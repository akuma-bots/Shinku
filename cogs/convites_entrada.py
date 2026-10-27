import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)
GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
ENTRY_CHANNEL_ID = int(os.getenv("NEMESIS_ENTRY_CHANNEL_ID", "1563995880623841331"))
INVITES_CHANNEL_ID = int(os.getenv("NEMESIS_INVITES_CHANNEL_ID", "1563995880623841332"))
COLOR = 0xB3132B


def make_entry_embed(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOVA PRESENÇA ・✦",
        description=(
            f"⟡・ **{discord.utils.escape_markdown(member.display_name)}**, seja bem-vindo(a) à NÊMESIS.\n"
            "Leia as regras, acompanhe os comunicados e explore os canais oficiais."
        ),
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="Ⅰ ━ PRIMEIROS PASSOS",
        value="➜ Leia as regras oficiais.\n➜ Confira anúncios e eventos.\n➜ Use os comandos de ajuda e tutorial disponíveis.",
        inline=False,
    )
    embed.add_field(
        name="Ⅱ ━ PARTICIPE E EVOLUA",
        value="⚔️ Participe de missões e desafios.\n◈ Consulte XP, ranking e Pontos de Contribuição (P.C.).\n⟡ Procure os canais oficiais de atendimento quando precisar.",
        inline=False,
    )
    embed.set_footer(text=f"NÊMESIS • Guia de entrada • Membro #{member.guild.member_count or 0}")
    return embed


class ConvitesEntrada(commands.Cog):
    """Guia de entrada e identificação aproximada de convites usados."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._uses: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._cache_ready = False

    async def _fetch(self, guild: discord.Guild):
        try:
            return await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            log.warning("Leitura de convites indisponível para guild=%s; verifique Gerenciar Servidor.", guild.id)
            return None

    async def _refresh(self, guild: discord.Guild):
        invites = await self._fetch(guild)
        if invites is not None:
            self._uses = {invite.code: (invite.uses or 0) for invite in invites}
            self._cache_ready = True
        return invites

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_ID)
        if guild and not self._cache_ready:
            async with self._lock:
                await self._refresh(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild and invite.guild.id == GUILD_ID:
            async with self._lock:
                await self._refresh(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild and invite.guild.id == GUILD_ID:
            async with self._lock:
                await self._refresh(invite.guild)

    async def _send_embed(self, guild: discord.Guild, channel_id: int, embed: discord.Embed):
        try:
            channel = guild.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise TypeError("O destino configurado não é um canal de texto.")
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, TypeError):
            log.exception("Não foi possível publicar no canal %s.", channel_id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != GUILD_ID or member.bot:
            return
        used = None
        async with self._lock:
            # Na primeira leitura, inicializamos a referência sem atribuir usos antigos
            # ao membro recém-chegado.
            if not self._cache_ready:
                await self._refresh(member.guild)
            else:
                previous = self._uses.copy()
                current = await self._refresh(member.guild)
                if current is not None:
                    increased = [
                        invite for invite in current
                        if (invite.uses or 0) > previous.get(invite.code, 0)
                    ]
                    # A atribuição é aproximada: entradas simultâneas podem ser ambíguas.
                    if len(increased) == 1:
                        used = increased[0]
        await asyncio.gather(
            self._send_embed(member.guild, ENTRY_CHANNEL_ID, make_entry_embed(member)),
            self._send_embed(member.guild, INVITES_CHANNEL_ID, self._make_invite_embed(member, used)),
        )

    @staticmethod
    def _make_invite_embed(member: discord.Member, invite: discord.Invite | None) -> discord.Embed:
        inviter = invite.inviter if invite else None
        embed = discord.Embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — REGISTRO DE RECRUTAMENTO ・✦",
            description=f"⟡・ {member.mention} entrou no servidor.",
            color=COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="NOVO MEMBRO", value=f"{discord.utils.escape_markdown(member.display_name)}\nID: {member.id}", inline=True)
        embed.add_field(name="CONVIDADO POR", value=inviter.mention if inviter else "Não identificado", inline=True)
        if invite:
            embed.add_field(name="CÓDIGO", value=invite.code, inline=True)
        embed.add_field(name="CONTA CRIADA", value=discord.utils.format_dt(member.created_at, style="R"), inline=True)
        embed.set_footer(text="A atribuição pode ser inconclusiva para links temporários ou convites simultâneos.")
        return embed

    @app_commands.command(name="convites", description="Consultar convites ativos criados por um membro.")
    @app_commands.guild_only()
    async def convites(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        if interaction.guild is None or interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Comando exclusivo da NÊMESIS.", ephemeral=True)
            return
        target = membro or interaction.user
        invites = await self._fetch(interaction.guild)
        if invites is None:
            await interaction.response.send_message("Não consegui ler os convites. Verifique a permissão Gerenciar Servidor.", ephemeral=True)
            return
        own = [i for i in invites if i.inviter and i.inviter.id == target.id]
        embed = discord.Embed(title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — PAINEL DE CONVITES ・✦", color=COLOR)
        embed.description = f"Convites ativos criados por {target.mention}. Links apagados não aparecem nesta contagem."
        embed.add_field(name="CONVITES ATIVOS", value=str(len(own)), inline=True)
        embed.add_field(name="USOS DOS LINKS ATIVOS", value=str(sum(i.uses or 0 for i in own)), inline=True)
        if own:
            embed.add_field(name="DETALHAMENTO", value="\n".join(f"• {i.code} — {i.uses or 0} uso(s)" for i in sorted(own, key=lambda x: x.uses or 0, reverse=True)[:10]), inline=False)
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(ConvitesEntrada(bot))
