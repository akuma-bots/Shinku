import asyncio
import logging
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
ARQUIVO_CONVITES = "convites_nemesis.json"


class ConvitesNemesis(commands.Cog):
    """Rastreia usos de convites e mantém contagem persistente por convidador."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._convites: dict[int, dict[str, tuple[int, int | None]]] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._inicializados: set[int] = set()

    async def _buscar_convites(self, guild: discord.Guild):
        try:
            convites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Não foi possível ler convites da guild=%s. Verifique Gerenciar servidor.",
                guild.id,
            )
            return None

        return {
            convite.code: (convite.uses or 0, convite.inviter.id if convite.inviter else None)
            for convite in convites
        }

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None or guild.id in self._inicializados:
            return
        cache = await self._buscar_convites(guild)
        if cache is not None:
            self._convites[guild.id] = cache
            self._inicializados.add(guild.id)
            logger.info("Cache de convites inicializado (guild=%s, convites=%s).", guild.id, len(cache))

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        async with self._locks[invite.guild.id]:
            self._convites.setdefault(invite.guild.id, {})[invite.code] = (
                invite.uses or 0, invite.inviter.id if invite.inviter else None
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        async with self._locks[invite.guild.id]:
            self._convites.setdefault(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if guild.id != GUILD_NEMESIS_ID or member.bot:
            return

        async with self._locks[guild.id]:
            anterior = self._convites.get(guild.id)
            atual = await self._buscar_convites(guild)
            if atual is None:
                return
            self._convites[guild.id] = atual
            if anterior is None:
                return

            usados = [
                (code, dados)
                for code, dados in atual.items()
                if code in anterior and dados[0] > anterior[code][0]
            ]
            # Se mais de um convite aumentou entre eventos, a atribuição é ambígua.
            if len(usados) != 1:
                logger.info(
                    "Convite não identificado com segurança (guild=%s, member=%s, candidatos=%s).",
                    guild.id, member.id, len(usados),
                )
                return

            code, (uses, inviter_id) = usados[0]
            if not inviter_id or inviter_id == member.id:
                return

            try:
                dados = await carregar(ARQUIVO_CONVITES, {})
                if not isinstance(dados, dict):
                    dados = {}
                servidor = dados.setdefault(str(guild.id), {})
                registro = servidor.setdefault(str(inviter_id), {"total": 0, "membros": []})
                membros = registro.setdefault("membros", [])
                # Idempotência: uma entrada não pode ser contabilizada duas vezes.
                if member.id not in membros:
                    membros.append(member.id)
                    registro["total"] = len(membros)
                    registro["ultimo_membro"] = member.id
                    registro["ultimo_codigo"] = code
                    await salvar(ARQUIVO_CONVITES, dados)
                    logger.info(
                        "Convite atribuído (guild=%s, inviter=%s, member=%s, code=%s).",
                        guild.id, inviter_id, member.id, code,
                    )
            except Exception:
                logger.exception("Falha ao salvar contagem de convites (guild=%s).", guild.id)

    @app_commands.command(name="meus-convites", description="Mostra quantas pessoas você trouxe para a NÊMESIS.")
    @app_commands.guild_only()
    async def meus_convites(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este comando só funciona na NÊMESIS.", ephemeral=True)
            return
        try:
            dados = await carregar(ARQUIVO_CONVITES, {})
            registro = dados.get(str(interaction.guild_id), {}).get(str(interaction.user.id), {})
            total = len(set(registro.get("membros", [])))
            embed = discord.Embed(
                title="✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — SEUS CONVITES・✦",
                description=f"Você trouxe **{total}** membro(s) identificado(s) para a organização.",
                color=0xB51F32,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="A contagem considera apenas convites identificados com segurança.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Falha ao consultar convites do usuário=%s.", interaction.user.id)
            await interaction.response.send_message(
                "Não consegui consultar seus convites agora. A equipe técnica foi avisada.",
                ephemeral=True,
            )

    @app_commands.command(name="ranking-convites", description="Mostra o ranking de convites identificados da NÊMESIS.")
    @app_commands.guild_only()
    async def ranking_convites(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este comando só funciona na NÊMESIS.", ephemeral=True)
            return
        try:
            dados = await carregar(ARQUIVO_CONVITES, {})
            servidor = dados.get(str(interaction.guild_id), {})
            ranking = sorted(
                ((user_id, len(set(item.get("membros", [])))) for user_id, item in servidor.items()),
                key=lambda item: item[1],
                reverse=True,
            )
            linhas = []
            for posicao, (user_id, total) in enumerate(ranking[:10], start=1):
                linhas.append(f"**{posicao}.** <@{user_id}> — **{total}** convite(s)")
            embed = discord.Embed(
                title="✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — RANKING DE CONVITES・✦",
                description="\n".join(linhas) if linhas else "Ainda não há convites contabilizados.",
                color=0xB51F32,
            )
            embed.set_footer(text="Convites sem atribuição segura não entram no ranking.")
            await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logger.exception("Falha ao montar ranking de convites.")
            await interaction.response.send_message(
                "Não consegui carregar o ranking agora. A equipe técnica foi avisada.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ConvitesNemesis(bot))
