import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar

log = logging.getLogger(__name__)
GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
HISTORY_CHANNEL_ID = int(os.getenv("NEMESIS_MEMBER_HISTORY_CHANNEL_ID", "1563995882540498997"))
HISTORY_FILE = "historico_membros_topicos.json"
COLOR = 0xB3132B


class HistoricoMembros(commands.Cog):
    """Mantém um tópico por membro e registra eventos relevantes da conta no servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache_lock = asyncio.Lock()

    def _lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _mapping(self) -> dict:
        dados = await carregar(HISTORY_FILE, {})
        return dados if isinstance(dados, dict) else {}

    async def _get_thread(self, guild_id: int, member_id: int):
        dados = await self._mapping()
        thread_id = (
            dados.get(str(guild_id), {}).get(str(member_id))
            if isinstance(dados.get(str(guild_id), {}), dict)
            else None
        )
        if not thread_id:
            return None
        try:
            thread = self.bot.get_channel(int(thread_id))
            if thread is None:
                thread = await self.bot.fetch_channel(int(thread_id))
            if isinstance(thread, discord.Thread):
                if thread.archived:
                    try:
                        await thread.edit(archived=False)
                    except discord.HTTPException:
                        pass
                return thread
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            log.warning("Tópico de histórico indisponível (guild=%s, member=%s).", guild_id, member_id)
        return None

    async def _save_thread_id(self, guild_id: int, member_id: int, thread_id: int):
        async with self._cache_lock:
            dados = await self._mapping()
            if not isinstance(dados.get(str(guild_id)), dict):
                dados[str(guild_id)] = {}
            dados[str(guild_id)][str(member_id)] = int(thread_id)
            await salvar(HISTORY_FILE, dados)

    async def _ensure_thread(self, member: discord.Member):
        key = f"{member.guild.id}:{member.id}"
        async with self._lock_for(key):
            existing = await self._get_thread(member.guild.id, member.id)
            if existing:
                return existing

            channel = member.guild.get_channel(HISTORY_CHANNEL_ID)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(HISTORY_CHANNEL_ID)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    log.exception("Canal de histórico não encontrado ou inacessível: %s", HISTORY_CHANNEL_ID)
                    return None

            if not isinstance(channel, discord.TextChannel):
                log.error("O canal de histórico %s precisa ser um canal de texto para criar tópicos.", HISTORY_CHANNEL_ID)
                return None

            embed = discord.Embed(
                title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — HISTÓRICO DO MEMBRO ・✦",
                description=(
                    f"⟡・ **Membro:** {discord.utils.escape_markdown(member.display_name)}\n"
                    f"**Usuário:** {discord.utils.escape_markdown(member.name)}\n"
                    f"**ID:** `{member.id}`\n"
                    f"**Conta criada:** {discord.utils.format_dt(member.created_at, style='F')}\n"
                    f"**Entrou no servidor:** {discord.utils.format_dt(member.joined_at, style='F') if member.joined_at else 'Data indisponível'}"
                ),
                color=COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Registro cronológico automático • NÊMESIS")
            try:
                starter = await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                thread = await starter.create_thread(
                    name=f"Histórico • {member.display_name} • {member.id}"[:100],
                    auto_archive_duration=10080,
                    reason="Criar tópico de histórico individual da NÊMESIS",
                )
                await self._save_thread_id(member.guild.id, member.id, thread.id)
                return thread
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Falha ao criar tópico de histórico para membro %s.", member.id)
                return None

    async def _record(self, member: discord.Member, event: str, details: str):
        if member.guild.id != GUILD_ID or member.bot:
            return
        thread = await self._ensure_thread(member)
        if thread is None:
            return
        embed = discord.Embed(
            title=event[:256],
            description=details[:4000],
            color=COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"{member} • {member.id}", icon_url=member.display_avatar.url)
        try:
            await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            log.exception("Não foi possível registrar evento no tópico %s.", thread.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._record(
            member,
            "↗️ Membro entrou",
            f"{member.mention} entrou no servidor.\nConta criada: {discord.utils.format_dt(member.created_at, style='F')}",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != GUILD_ID or member.bot:
            return
        thread = await self._get_thread(member.guild.id, member.id)
        if thread is None:
            # Se o membro já tinha um tópico, a remoção deve ser registrada nele.
            return
        embed = discord.Embed(
            title="↘️ Membro saiu do servidor",
            description=(
                f"**Usuário:** {discord.utils.escape_markdown(member.name)}\n"
                f"**ID:** `{member.id}`\n"
                "O evento de saída não permite distinguir, por si só, saída voluntária, expulsão ou banimento."
            ),
            color=COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            log.exception("Não foi possível registrar a saída do membro %s.", member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.guild.id != GUILD_ID or after.bot:
            return

        changes = []
        if before.nick != after.nick:
            antigo = before.nick or before.name
            novo = after.nick or after.name
            changes.append(
                f"**Apelido:** {discord.utils.escape_markdown(antigo)} → "
                f"{discord.utils.escape_markdown(novo)}"
            )

        before_roles = {role.id: role for role in before.roles if role.name != "@everyone"}
        after_roles = {role.id: role for role in after.roles if role.name != "@everyone"}
        added = [role for role_id, role in after_roles.items() if role_id not in before_roles]
        removed = [role for role_id, role in before_roles.items() if role_id not in after_roles]
        if added:
            changes.append("**Cargos adicionados:** " + ", ".join(discord.utils.escape_markdown(r.name) for r in added[:20]))
        if removed:
            changes.append("**Cargos removidos:** " + ", ".join(discord.utils.escape_markdown(r.name) for r in removed[:20]))

        if changes:
            await self._record(after, "⚙️ Alteração no membro", "\n".join(changes))

    @app_commands.command(name="historico-membro", description="Consultar o tópico de histórico de um membro.")
    @app_commands.guild_only()
    @app_commands.describe(membro="Membro cujo histórico deseja consultar")
    async def historico_membro(self, interaction: discord.Interaction, membro: discord.Member):
        if interaction.guild_id != GUILD_ID or interaction.guild is None:
            await interaction.response.send_message("Comando exclusivo da NÊMESIS.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not (
            interaction.user.guild_permissions.view_audit_log
            or interaction.user.guild_permissions.manage_guild
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "Você precisa de permissão para ver o registro de auditoria para consultar históricos.",
                ephemeral=True,
            )
            return

        thread = await self._get_thread(interaction.guild.id, membro.id)
        if thread is None:
            await interaction.response.send_message(
                "Esse membro ainda não possui um tópico de histórico. Um tópico será criado quando ocorrer um evento registrado.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"📚 Histórico de {membro.mention}: {thread.mention}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(HistoricoMembros(bot))
