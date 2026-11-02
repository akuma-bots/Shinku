import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.progressao_gangue import ARQUIVO as ARQUIVO_PROGRESSAO, CARGO_NEMESIS_ID
from utils.apresentacao import aplicar_identidade_servidor, criar_embed
from utils.perfis import get_perfil
from utils.revisoes import listar as listar_revisoes
from utils.storage import carregar
from utils import conquistas as conquistas_storage

log = logging.getLogger(__name__)

CANAL_CONQUISTAS_ID = 1563995881508831339
COR_NEMESIS = 0x9F1239


def _inteiro(valor) -> int:
    try:
        return max(0, int(valor or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def montar_estatisticas(progressao: dict, competitivo: dict, revisoes: list, user_id: int) -> dict:
    progressao = progressao if isinstance(progressao, dict) else {}
    competitivo = competitivo if isinstance(competitivo, dict) else {}
    aprovadas = sum(
        1 for item in revisoes
        if isinstance(item, dict)
        and (
            str(item.get("autor_id")) == str(user_id)
            or str(item.get("auxiliar_id")) == str(user_id)
        )
        and item.get("status") == "aprovada"
        and str(item.get("tipo", "")).lower() in {"missao", "contribuicao", "especial", "pve"}
    )
    return {
        "xp": _inteiro(progressao.get("xp")),
        "mensagens": _inteiro(progressao.get("mensagens")),
        "missoes": aprovadas,
        "guerras": _inteiro(progressao.get("guerras")),
        "vitorias": _inteiro(competitivo.get("vitorias")),
        "mvps": _inteiro(competitivo.get("mvps")),
        "maior_sequencia": _inteiro(competitivo.get("maior_sequencia")),
    }


def _barra(valor: int, meta: int) -> str:
    percentual = min(1.0, max(0.0, valor / max(1, meta)))
    preenchido = int(percentual * 8)
    return "▰" * preenchido + "▱" * (8 - preenchido)


class Conquistas(commands.Cog):
    """Conquistas verificáveis, permanentes e com recompensas idempotentes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _estatisticas(self, guild: discord.Guild, user_id: int) -> dict:
        dados = await carregar(ARQUIVO_PROGRESSAO, {})
        guild_data = dados.get(str(guild.id), {}) if isinstance(dados, dict) else {}
        membros = guild_data.get("membros", {}) if isinstance(guild_data, dict) else {}
        progressao = membros.get(str(user_id), {}) if isinstance(membros, dict) else {}
        competitivo = await get_perfil(guild.id, user_id)
        revisoes = await listar_revisoes(guild.id)
        return montar_estatisticas(progressao, competitivo, revisoes, user_id)

    async def _processar(self, guild: discord.Guild, membro: discord.Member, anunciar: bool = True) -> list[dict]:
        if not any(cargo.id == CARGO_NEMESIS_ID for cargo in membro.roles):
            return []
        estatisticas = await self._estatisticas(guild, membro.id)
        novos, pendentes = await conquistas_storage.registrar_desbloqueios(
            guild.id, membro.id, estatisticas
        )

        progressao = self.bot.get_cog("ProgressaoGangue")
        if progressao is not None:
            for conquista in pendentes:
                try:
                    await progressao.registrar_recompensa(
                        guild=guild,
                        user_id=membro.id,
                        quantidade=int(conquista["recompensa_xp"]),
                        tipo="conquista",
                        evento_id=f"conquista:{conquista['id']}",
                    )
                    await conquistas_storage.marcar_recompensa_aplicada(
                        guild.id, membro.id, conquista["id"]
                    )
                except Exception:
                    log.exception(
                        "Falha ao entregar recompensa da conquista %s ao membro %s.",
                        conquista["id"], membro.id,
                    )

        if novos and anunciar:
            from utils.registro_global import registrar as registrar_global
            for conquista in novos:
                detalhe = (
                    f"**Membro:** {membro.mention} (ID: {membro.id})\n"
                    f"**Conquista:** {conquista['icone']} {conquista['nome']}\n"
                    f"**Raridade:** {conquista['raridade']}\n"
                    f"**Recompensa:** +{conquista['recompensa_xp']} XP"
                )
                await registrar_global(
                    guild,
                    "conquistas",
                    "Conquista desbloqueada",
                    detalhe,
                    cor=COR_NEMESIS,
                )
                await registrar_global(
                    guild,
                    "historico_membros",
                    "Conquista pessoal desbloqueada",
                    detalhe,
                    cor=COR_NEMESIS,
                )

            canal = guild.get_channel(CANAL_CONQUISTAS_ID)
            if isinstance(canal, discord.TextChannel):
                embed = criar_embed(
                    title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ CONQUISTA DESBLOQUEADA",
                    description=(
                        f"**{membro.mention}** ampliou seu histórico na organização.\n"
                        "Uma nova marca foi registrada permanentemente."
                    ),
                    color=COR_NEMESIS,
                    timestamp=discord.utils.utcnow(),
                )
                for conquista in novos:
                    embed.add_field(
                        name=f"{conquista['icone']}  {conquista['nome']} · {conquista['raridade']}",
                        value=(
                            f"{conquista['descricao']}\n"
                            f"**Recompensa:** +{conquista['recompensa_xp']} XP organizacionais"
                        ),
                        inline=False,
                    )
                aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
                embed.set_footer(text="NÊMESIS • MÉRITO REGISTRADO • Conquistas permanentes")
                try:
                    await canal.send(
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Não foi possível publicar o desbloqueio no canal de conquistas.")
        return novos

    @commands.Cog.listener()
    async def on_nemesis_conquistas_verificar(self, guild_id: int, user_id: int):
        guild = self.bot.get_guild(int(guild_id))
        membro = guild.get_member(int(user_id)) if guild else None
        if guild is None or membro is None:
            return
        await self._processar(guild, membro)

    @app_commands.command(name="conquistas", description="Consulta conquistas, medalhas e progresso de um membro.")
    @app_commands.describe(membro="Membro para consultar; padrão: você")
    async def conquistas(self, interaction: discord.Interaction, membro: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.", ephemeral=True
            )
            return
        alvo = membro or interaction.user
        await interaction.response.defer(ephemeral=True, thinking=True)
        novos = await self._processar(interaction.guild, alvo)
        estatisticas = await self._estatisticas(interaction.guild, alvo.id)
        desbloqueadas = await conquistas_storage.listar_desbloqueadas(
            interaction.guild.id, alvo.id
        )

        embed = criar_embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ DOSSIÊ DE CONQUISTAS",
            description=(
                f"**Integrante:** {alvo.mention}\n"
                f"**Marcos desbloqueados:** {len(desbloqueadas)}/{len(conquistas_storage.CATALOGO_CONQUISTAS)}\n"
                f"**Recompensas:** XP organizacional, medalhas e reconhecimento permanente."
            ),
            color=COR_NEMESIS,
            timestamp=discord.utils.utcnow(),
        )
        aplicar_identidade_servidor(embed, interaction.guild, self.bot, banner=True)
        for conquista in conquistas_storage.CATALOGO_CONQUISTAS:
            registro = desbloqueadas.get(conquista["id"])
            valor = estatisticas.get(conquista["campo"], 0)
            if registro:
                status = "✓ DESBLOQUEADA"
                data = int(registro.get("desbloqueada_em", 0) or 0)
                detalhe = f"**{status}**"
                if data:
                    detalhe += f" · <t:{data}:d>"
                detalhe += f"\nRecompensa: +{conquista['recompensa_xp']} XP"
            else:
                detalhe = (
                    f"**{min(valor, conquista['meta']):,}/{conquista['meta']:,}**".replace(",", ".")
                    + f"\n{_barra(valor, conquista['meta'])} · {conquista['raridade']}"
                )
            embed.add_field(
                name=f"{conquista['icone']}  {conquista['nome']}",
                value=f"{conquista['descricao']}\n{detalhe}",
                inline=True,
            )
        embed.set_footer(text="NÊMESIS • CONQUISTAS • Critérios validados automaticamente")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Conquistas(bot))
