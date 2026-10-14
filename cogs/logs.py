import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils.guild_config import get_config


logger = logging.getLogger(__name__)


class Logs(commands.Cog):
    """Registra eventos do servidor (entradas, saídas, edições e exclusões de mensagem)
    no canal de logs configurado por cada servidor via /configurar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _canal_logs(self, guild: discord.Guild):
        try:
            config = await get_config(guild.id)
            log_id = config.get("log_channel_id")
            if not log_id:
                logger.debug("Canal de logs não configurado (guild=%s).", guild.id)
                return None
            canal = guild.get_channel(int(log_id))
            if canal is None:
                try:
                    canal = await self.bot.fetch_channel(int(log_id))
                except (discord.NotFound, discord.Forbidden):
                    logger.warning("Canal de logs indisponível (guild=%s, channel=%s).", guild.id, log_id)
                    return None
            if not hasattr(canal, "send"):
                logger.warning("Destino de logs não aceita mensagens (guild=%s, channel=%s).", guild.id, log_id)
                return None
            return canal
        except Exception:
            logger.exception("Não foi possível resolver o canal de logs (guild=%s).", guild.id)
            return None

    async def _enviar_log(self, canal, embed: discord.Embed):
        """Falhas no canal de auditoria não podem derrubar listeners do bot."""
        try:
            if embed.timestamp is None:
                embed.timestamp = datetime.now(timezone.utc)
            if not embed.footer.text:
                embed.set_footer(text="NÊMESIS • Registro de auditoria")
            await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return True
        except discord.Forbidden:
            logger.warning("Sem permissão para publicar log (channel=%s).", getattr(canal, "id", "desconhecido"))
        except discord.HTTPException:
            logger.exception("Falha HTTP ao publicar log (channel=%s).", getattr(canal, "id", "desconhecido"))
        except Exception:
            logger.exception("Erro inesperado ao publicar log (channel=%s).", getattr(canal, "id", "desconhecido"))
        return False

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        conta_criada = discord.utils.format_dt(member.created_at, style="R")
        embed = discord.Embed(
            description=f"📥 {member.mention} entrou no servidor.\nConta criada {conta_criada}.",
            color=0x57F287,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        embed = discord.Embed(description=f"📤 {member.mention} saiu do servidor.", color=0xED4245)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        canal = await self._canal_logs(message.guild)
        if not canal or canal.id == message.channel.id:
            return  # evita loop se o canal de logs for o mesmo onde a mensagem foi apagada
        conteudo = message.content or "*(sem texto)*"
        anexos = "\\n".join(
            f"[{anexo.filename}]({anexo.url})" for anexo in message.attachments[:8]
        )
        descricao = (
            f"**Autor:** {message.author.mention} ({message.author.id})\\n"
            f"**Canal:** {message.channel.mention}\\n"
            f"**Mensagem:**\\n{conteudo[:1200]}"
        )
        if anexos:
            descricao += f"\\n**Anexos:**\\n{anexos[:1200]}"
        embed = discord.Embed(description=descricao[:4000], color=0xED4245)
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, antes: discord.Message, depois: discord.Message):
        if antes.author.bot or not antes.guild:
            return
        anexos_antes = [anexo.url for anexo in antes.attachments]
        anexos_depois = [anexo.url for anexo in depois.attachments]
        if antes.content == depois.content and anexos_antes == anexos_depois:
            return
        canal = await self._canal_logs(antes.guild)
        if not canal:
            return
        embed = discord.Embed(
            description=(
                f"✏️ {antes.author.mention} editou uma mensagem em {antes.channel.mention}:\n"
                f"**Antes:** {antes.content[:700] or '*vazio*'}\n"
                f"**Depois:** {depois.content[:700] or '*vazio*'}"
            ),
            color=0xFEE75C,
        )
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = discord.Embed(description=f"🔨 {user.mention} (`{user}`) foi banido do servidor.", color=0xED4245)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = discord.Embed(description=f"⚖️ {user.mention} (`{user}`) foi desbanido do servidor.", color=0x57F287)
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_member_update(self, antes: discord.Member, depois: discord.Member):
        canal = await self._canal_logs(depois.guild)
        if not canal:
            return

        if antes.nick != depois.nick:
            embed = discord.Embed(
                description=f"📝 {depois.mention} mudou de apelido: `{antes.nick or antes.name}` → `{depois.nick or depois.name}`",
                color=0xFEE75C,
            )
            await self._enviar_log(canal, embed)

        cargos_antes = set(antes.roles)
        cargos_depois = set(depois.roles)
        ganhos = cargos_depois - cargos_antes
        perdidos = cargos_antes - cargos_depois
        for cargo in ganhos:
            if cargo.is_default():
                continue
            await self._enviar_log(canal, discord.Embed(description=f"➕ {depois.mention} recebeu o cargo {cargo.mention}.", color=0x57F287))
        for cargo in perdidos:
            if cargo.is_default():
                continue
            await self._enviar_log(canal, discord.Embed(description=f"➖ {depois.mention} perdeu o cargo {cargo.mention}.", color=0xED4245))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await self._enviar_log(canal, discord.Embed(description=f"📁 Canal criado: **{channel.name}** ({channel.type}).", color=0x57F287))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await self._enviar_log(canal, discord.Embed(description=f"🗑️ Canal apagado: **{channel.name}** ({channel.type}).", color=0xED4245))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        if antes.channel is None and depois.channel is not None:
            await self._enviar_log(canal, discord.Embed(description=f"🔊 {member.mention} entrou no canal de voz **{depois.channel.name}**.", color=0x57F287))
        elif antes.channel is not None and depois.channel is None:
            await self._enviar_log(canal, discord.Embed(description=f"🔇 {member.mention} saiu do canal de voz **{antes.channel.name}**.", color=0xED4245))
        elif antes.channel != depois.channel:
            await self._enviar_log(canal, discord.Embed(description=f"🔀 {member.mention} mudou de **{antes.channel.name}** para **{depois.channel.name}**.", color=0xFEE75C))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
