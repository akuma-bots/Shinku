import re
import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import get_config
from utils.perfis import (
    registrar_resultado_guerra,
    calcular_patente_atual,
    definir_patente,
)


ARQUIVO_GUERRAS = "guerras.json"


def _extrair_mencoes(texto: str) -> list:
    if not texto:
        return []

    return [
        int(m)
        for m in re.findall(r"<@!?(\\d+)>", texto)
    ]


class Guerras(commands.Cog):
    """
    Sistema de guerras da NÊMESIS.

    Os registros ficam persistidos em guerras.json, permitindo ao
    Dashboard acessar o histórico, temporadas, participantes,
    resultados e guerras agendadas.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dados_guild(self, guild_id: int) -> dict:
        todos = await carregar(
            ARQUIVO_GUERRAS,
            {},
        )

        dados = todos.get(
            str(guild_id),
            {
                "guild_id": guild_id,
                "temporada_atual": 1,
                "guerras": [],
                "agendamentos": [],
            },
        )

        dados.setdefault("guild_id", guild_id)
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])

        return dados

    async def _salvar_dados_guild(
        self,
        guild_id: int,
        dados: dict,
    ):
        todos = await carregar(
            ARQUIVO_GUERRAS,
            {},
        )

        dados["guild_id"] = guild_id
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])

        todos[str(guild_id)] = dados

        await salvar(
            ARQUIVO_GUERRAS,
            todos,
        )

    @app_commands.command(
        name="guerra-agendar",
        description="Anuncia uma guerra agendada entre duas gangues.",
    )
    @app_commands.describe(
        gangue_a="Nome da primeira gangue",
        gangue_b="Nome da segunda gangue",
        quando="Quando vai ser (texto livre, ex: 'sábado 20h')",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def guerra_agendar(
        self,
        interaction: discord.Interaction,
        gangue_a: str,
        gangue_b: str,
        quando: str,
    ):
        config = await get_config(
            interaction.guild.id
        )

        # Canal oficial de guerras da NÊMESIS.
        canal_id = config.get("canal_guerras_id")

        canal = (
            interaction.guild.get_channel(canal_id)
            if canal_id
            else interaction.channel
        )

        if canal is None:
            await interaction.response.send_message(
                "❌ O canal oficial de guerras não foi encontrado.",
                ephemeral=True,
            )
            return

        registro_id = str(uuid.uuid4())[:8]

        agendamento = {
            "id": registro_id,
            "guild_id": interaction.guild.id,
            "gangue_a": gangue_a,
            "gangue_b": gangue_b,
            "quando": quando,
            "agendado_por_id": interaction.user.id,
            "canal_id": canal.id,
            "timestamp": time.time(),
            "status": "agendada",
        }

        dados = await self._dados_guild(
            interaction.guild.id
        )

        dados["agendamentos"].append(
            agendamento
        )

        embed = discord.Embed(
            title="⚔️ Guerra agendada!",
            description=(
                f"**{gangue_a}** vs **{gangue_b}**"
            ),
            color=0xED4245,
        )

        embed.add_field(
            name="Quando",
            value=quando,
        )

        embed.add_field(
            name="ID",
            value=f"`{registro_id}`",
            inline=True,
        )

        embed.set_footer(
            text=f"Agendada por {interaction.user}"
        )

        try:
            mensagem = await canal.send(
                embed=embed
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para enviar mensagens no canal oficial de guerras.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Não foi possível publicar a guerra no canal oficial.",
                ephemeral=True,
            )
            return

        agendamento["mensagem_id"] = mensagem.id

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        await interaction.response.send_message(
            f"✅ Guerra anunciada em {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="guerra-registrar",
        description="Registra o resultado de uma guerra já disputada.",
    )
    @app_commands.describe(
        gangue_a="Nome da primeira gangue",
        gangue_b="Nome da segunda gangue",
        placar_a="Placar da gangue A",
        placar_b="Placar da gangue B",
        mvp="Quem foi o MVP da guerra (opcional)",
        participantes_a="Mencione os participantes da gangue A, separados por espaço",
        participantes_b="Mencione os participantes da gangue B, separados por espaço",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def guerra_registrar(
        self,
        interaction: discord.Interaction,
        gangue_a: str,
        gangue_b: str,
        placar_a: int,
        placar_b: int,
        mvp: discord.Member = None,
        participantes_a: str = None,
        participantes_b: str = None,
    ):
        await interaction.response.defer()

        if placar_a > placar_b:
            vencedor = gangue_a
        elif placar_b > placar_a:
            vencedor = gangue_b
        else:
            vencedor = "Empate"

        ids_a = _extrair_mencoes(
            participantes_a
        )

        ids_b = _extrair_mencoes(
            participantes_b
        )

        medalhas_ganhas_texto = []
        promocoes_texto = []

        async def _processar(
            ids,
            gangue,
            venceu,
        ):
            for user_id in ids:
                foi_mvp = (
                    mvp is not None
                    and mvp.id == user_id
                )

                resultado = (
                    await registrar_resultado_guerra(
                        interaction.guild.id,
                        user_id,
                        venceu,
                        foi_mvp,
                    )
                )

                if resultado["medalhas_novas"]:
                    medalhas_ganhas_texto.append(
                        f"<@{user_id}>: "
                        f"{', '.join(resultado['medalhas_novas'])}"
                    )

                nova_patente = (
                    await calcular_patente_atual(
                        interaction.guild.id,
                        resultado["perfil"]["xp"],
                    )
                )

                if (
                    nova_patente
                    and nova_patente["nome"]
                    != resultado["patente_antiga"]
                ):
                    await definir_patente(
                        interaction.guild.id,
                        user_id,
                        nova_patente["nome"],
                    )

                    membro = (
                        interaction.guild.get_member(
                            user_id
                        )
                    )

                    cargo_id = nova_patente.get(
                        "cargo_id"
                    )

                    if membro and cargo_id:
                        cargo = (
                            interaction.guild.get_role(
                                cargo_id
                            )
                        )

                        if cargo:
                            try:
                                await membro.add_roles(
                                    cargo,
                                    reason=(
                                        "Promoção automática "
                                        "de patente"
                                    ),
                                )
                            except discord.Forbidden:
                                pass

                    promocoes_texto.append(
                        f"<@{user_id}> → "
                        f"**{nova_patente['nome']}**"
                    )

        await _processar(
            ids_a,
            gangue_a,
            vencedor == gangue_a,
        )

        await _processar(
            ids_b,
            gangue_b,
            vencedor == gangue_b,
        )

        dados = await self._dados_guild(
            interaction.guild.id
        )

        registro = {
            "id": str(uuid.uuid4())[:8],
            "guild_id": interaction.guild.id,
            "gangue_a": gangue_a,
            "gangue_b": gangue_b,
            "placar_a": placar_a,
            "placar_b": placar_b,
            "vencedor": vencedor,
            "mvp_id": mvp.id if mvp else None,
            "participantes_a": ids_a,
            "participantes_b": ids_b,
            "temporada": dados["temporada_atual"],
            "registrado_por_id": interaction.user.id,
            "timestamp": time.time(),
            "status": "finalizada",
        }

        dados["guerras"].append(
            registro
        )

        for agendamento in reversed(
            dados["agendamentos"]
        ):
            if (
                agendamento.get("status")
                == "agendada"
                and agendamento.get("gangue_a", "").lower()
                == gangue_a.lower()
                and agendamento.get("gangue_b", "").lower()
                == gangue_b.lower()
            ):
                agendamento["status"] = "finalizada"
                agendamento["guerra_id"] = registro["id"]
                break

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        embed = discord.Embed(
            title="🏆 Resultado registrado",
            description=(
                f"**{gangue_a}** {placar_a} x "
                f"{placar_b} **{gangue_b}**\n"
                f"Vencedor: **{vencedor}**"
            ),
            color=0x57F287,
        )

        if mvp:
            embed.add_field(
                name="MVP",
                value=mvp.mention,
                inline=False,
            )

        if medalhas_ganhas_texto:
            embed.add_field(
                name="🎖️ Medalhas conquistadas",
                value="\n".join(
                    medalhas_ganhas_texto
                ),
                inline=False,
            )

        if promocoes_texto:
            embed.add_field(
                name="⬆️ Promoções",
                value="\n".join(
                    promocoes_texto
                ),
                inline=False,
            )

        await interaction.followup.send(
            embed=embed
        )

    @app_commands.command(
        name="guerra-historico",
        description="Mostra as últimas guerras registradas.",
    )
    @app_commands.describe(
        gangue="(Opcional) filtra só guerras dessa gangue"
    )
    async def guerra_historico(
        self,
        interaction: discord.Interaction,
        gangue: str = None,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        guerras = dados["guerras"]

        if gangue:
            guerras = [
                g
                for g in guerras
                if gangue.lower()
                in g["gangue_a"].lower()
                or gangue.lower()
                in g["gangue_b"].lower()
            ]

        guerras = sorted(
            guerras,
            key=lambda g: g["timestamp"],
            reverse=True,
        )[:10]

        if not guerras:
            await interaction.response.send_message(
                "Nenhuma guerra registrada ainda.",
                ephemeral=True,
            )
            return

        linhas = [
            (
                f"**{g['gangue_a']}** "
                f"{g['placar_a']} x "
                f"{g['placar_b']} "
                f"**{g['gangue_b']}** — "
                f"vencedor: {g['vencedor']} "
                f"(temporada {g['temporada']})"
            )
            for g in guerras
        ]

        embed = discord.Embed(
            title="📜 Histórico de guerras",
            description="\n".join(linhas),
            color=0x5865F2,
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="temporada-nova",
        description=(
            "Encerra a temporada atual e começa uma nova "
            "(o histórico não é apagado)."
        ),
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def temporada_nova(
        self,
        interaction: discord.Interaction,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        dados["temporada_atual"] += 1

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        await interaction.response.send_message(
            f"🆕 Temporada **{dados['temporada_atual']}** começou! "
            "O histórico de temporadas anteriores continua salvo."
        )

    @app_commands.command(
        name="ranking-temporada",
        description="Ranking de vitórias em guerras de uma temporada.",
    )
    @app_commands.describe(
        temporada="Número da temporada (padrão: a atual)"
    )
    async def ranking_temporada(
        self,
        interaction: discord.Interaction,
        temporada: int = None,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        alvo = (
            temporada
            or dados["temporada_atual"]
        )

        guerras_da_temporada = [
            g
            for g in dados["guerras"]
            if g["temporada"] == alvo
        ]

        contagem = {}

        for guerra in guerras_da_temporada:
            vencedores_ids = (
                guerra["participantes_a"]
                if guerra["vencedor"]
                == guerra["gangue_a"]
                else (
                    guerra["participantes_b"]
                    if guerra["vencedor"]
                    == guerra["gangue_b"]
                    else []
                )
            )

            for uid in vencedores_ids:
                contagem[uid] = (
                    contagem.get(uid, 0) + 1
                )

        if not contagem:
            await interaction.response.send_message(
                f"Nenhum resultado registrado "
                f"na temporada {alvo} ainda.",
                ephemeral=True,
            )
            return

        top = sorted(
            contagem.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        linhas = [
            f"**#{i + 1}** <@{uid}> — "
            f"{vitorias} vitória(s)"
            for i, (uid, vitorias)
            in enumerate(top)
        ]

        embed = discord.Embed(
            title=f"🏆 Ranking — Temporada {alvo}",
            description="\n".join(linhas),
            color=0xFEE75C,
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(
        Guerras(bot)
    )