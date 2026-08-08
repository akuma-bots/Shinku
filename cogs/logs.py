import discord
from discord.ext import commands
from utils.guild_config import get_config


class Logs(commands.Cog):
    """Registra eventos do servidor (entradas, saídas, edições e exclusões de mensagem)
    no canal de logs configurado por cada servidor via /configurar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _canal_logs(self, guild: discord.Guild):
        config = await get_config(guild.id)
        log_id = config["log_channel_id"]
        if not log_id:
            return None
        return guild.get_channel(log_id)

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
        await canal.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        embed = discord.Embed(description=f"📤 {member.mention} saiu do servidor.", color=0xED4245)
        embed.set_thumbnail(url=member.display_avatar.url)
        await canal.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        canal = await self._canal_logs(message.guild)
        if not canal or canal.id == message.channel.id:
            return  # evita loop se o canal de logs for o mesmo onde a mensagem foi apagada
        conteudo = message.content or "*(sem texto — pode ser um anexo)*"
        embed = discord.Embed(
            description=f"🗑️ Mensagem de {message.author.mention} apagada em {message.channel.mention}:\n{conteudo[:500]}",
            color=0xED4245,
        )
        await canal.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, antes: discord.Message, depois: discord.Message):
        if antes.author.bot or not antes.guild or antes.content == depois.content:
            return
        canal = await self._canal_logs(antes.guild)
        if not canal:
            return
        embed = discord.Embed(
            description=(
                f"✏️ {antes.author.mention} editou uma mensagem em {antes.channel.mention}:\n"
                f"**Antes:** {antes.content[:400] or '*vazio*'}\n"
                f"**Depois:** {depois.content[:400] or '*vazio*'}"
            ),
            color=0xFEE75C,
        )
        await canal.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = discord.Embed(description=f"🔨 {user.mention} (`{user}`) foi banido do servidor.", color=0xED4245)
        embed.set_thumbnail(url=user.display_avatar.url)
        await canal.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = discord.Embed(description=f"⚖️ {user.mention} (`{user}`) foi desbanido do servidor.", color=0x57F287)
        await canal.send(embed=embed)

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
            await canal.send(embed=embed)

        cargos_antes = set(antes.roles)
        cargos_depois = set(depois.roles)
        ganhos = cargos_depois - cargos_antes
        perdidos = cargos_antes - cargos_depois
        for cargo in ganhos:
            if cargo.is_default():
                continue
            await canal.send(embed=discord.Embed(description=f"➕ {depois.mention} recebeu o cargo {cargo.mention}.", color=0x57F287))
        for cargo in perdidos:
            if cargo.is_default():
                continue
            await canal.send(embed=discord.Embed(description=f"➖ {depois.mention} perdeu o cargo {cargo.mention}.", color=0xED4245))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await canal.send(embed=discord.Embed(description=f"📁 Canal criado: **{channel.name}** ({channel.type}).", color=0x57F287))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await canal.send(embed=discord.Embed(description=f"🗑️ Canal apagado: **{channel.name}** ({channel.type}).", color=0xED4245))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        if antes.channel is None and depois.channel is not None:
            await canal.send(embed=discord.Embed(description=f"🔊 {member.mention} entrou no canal de voz **{depois.channel.name}**.", color=0x57F287))
        elif antes.channel is not None and depois.channel is None:
            await canal.send(embed=discord.Embed(description=f"🔇 {member.mention} saiu do canal de voz **{antes.channel.name}**.", color=0xED4245))
        elif antes.channel != depois.channel:
            await canal.send(embed=discord.Embed(description=f"🔀 {member.mention} mudou de **{antes.channel.name}** para **{depois.channel.name}**.", color=0xFEE75C))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
