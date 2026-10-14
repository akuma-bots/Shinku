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
        anexos = "\n".join(
            f"[{anexo.filename}]({anexo.url})" for anexo in message.attachments[:8]
        )
        descricao = (
            f"**Autor:** {message.author.mention} ({message.author.id})\n"
            f"**Canal:** {message.channel.mention}\n"
            f"**Mensagem:**\n{conteudo[:1200]}"
        )
        if anexos:
            descricao += f"\n**Anexos:**\n{anexos[:1200]}"
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
        embed = discord.Embed(
            title="Mensagem editada",
            description=(
                f"**Autor:** {antes.author.mention} ({antes.author.id})\n"
                f"**Canal:** {antes.channel.mention} ({antes.channel.id})\n"
                f"**Antes:**\n{antes.content[:1000] or '*vazio*'}\n"
                f"**Depois:**\n{depois.content[:1000] or '*vazio*'}"
            ),
            color=0xFEE75C,
        )
        if anexos_antes != anexos_depois:
            antigos = "\n".join(f"[{a.filename}]({a.url})" for a in antes.attachments[:6]) or "*(nenhum)*"
            atuais = "\n".join(f"[{a.filename}]({a.url})" for a in depois.attachments[:6]) or "*(nenhum)*"
            embed.add_field(name="Anexos anteriores", value=antigos[:1024], inline=False)
            embed.add_field(name="Anexos atuais", value=atuais[:1024], inline=False)
        embed.add_field(name="ID da mensagem", value=str(antes.id), inline=True)
        canal = await self._canal_logs(antes.guild)
        if canal and canal.id != antes.channel.id:
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
                title="Apelido alterado",
                description=(
                    f"**Membro:** {depois.mention} ({depois.id})\n"
                    f"**Antes:** {antes.nick or antes.name}\n"
                    f"**Depois:** {depois.nick or depois.name}"
                ),
                color=0xFEE75C,
            )
            await self._enviar_log(canal, embed)

        ids_antes = {cargo.id: cargo for cargo in antes.roles if not cargo.is_default()}
        ids_depois = {cargo.id: cargo for cargo in depois.roles if not cargo.is_default()}
        ganhos = [cargo for cargo_id, cargo in ids_depois.items() if cargo_id not in ids_antes]
        perdidos = [cargo for cargo_id, cargo in ids_antes.items() if cargo_id not in ids_depois]
        if ganhos or perdidos:
            embed = discord.Embed(
                title="Cargos do membro alterados",
                description=f"**Membro:** {depois.mention} ({depois.id})",
                color=0xB3132B,
            )
            if ganhos:
                embed.add_field(
                    name=f"Cargos recebidos ({len(ganhos)})",
                    value=" ".join(cargo.mention for cargo in ganhos)[:1024],
                    inline=False,
                )
            if perdidos:
                embed.add_field(
                    name=f"Cargos removidos ({len(perdidos)})",
                    value=" ".join(cargo.mention for cargo in perdidos)[:1024],
                    inline=False,
                )
            await self._enviar_log(canal, embed)

        if antes.communication_disabled_until != depois.communication_disabled_until:
            embed = discord.Embed(
                title="Timeout alterado",
                description=f"**Membro:** {depois.mention} ({depois.id})",
                color=0xFEE75C,
            )
            embed.add_field(
                name="Antes",
                value=discord.utils.format_dt(antes.communication_disabled_until, style="F")
                if antes.communication_disabled_until else "Sem timeout",
                inline=True,
            )
            embed.add_field(
                name="Depois",
                value=discord.utils.format_dt(depois.communication_disabled_until, style="F")
                if depois.communication_disabled_until else "Sem timeout",
                inline=True,
            )
            await self._enviar_log(canal, embed)

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


    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        mensagens = [m for m in messages if m.guild and not m.author.bot]
        if not mensagens:
            return
        agrupadas = {}
        for mensagem in mensagens:
            agrupadas.setdefault(mensagem.channel, []).append(mensagem)
        guild = mensagens[0].guild
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = discord.Embed(
            title="Exclusão em massa de mensagens",
            description=f"Foram removidas {len(mensagens)} mensagens em {len(agrupadas)} canal(is).",
            color=0xED4245,
        )
        for origem, itens in list(agrupadas.items())[:8]:
            linhas = [
                f"• {discord.utils.escape_markdown(str(m.author))}: {(m.content or '(sem texto)')[:120]}"
                for m in itens[:5]
            ]
            embed.add_field(
                name=f"Canal: {origem.name} ({len(itens)} mensagens)",
                value="\n".join(linhas)[:1024] or "Sem conteúdo textual.",
                inline=False,
            )
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, antes: discord.abc.GuildChannel, depois: discord.abc.GuildChannel):
        mudancas = []
        if antes.name != depois.name:
            mudancas.append(f"Nome: {antes.name} → {depois.name}")
        if antes.category_id != depois.category_id:
            categoria_antes = antes.category.name if antes.category else "Nenhuma"
            categoria_depois = depois.category.name if depois.category else "Nenhuma"
            mudancas.append(f"Categoria: {categoria_antes} → {categoria_depois}")
        if isinstance(antes, discord.TextChannel) and isinstance(depois, discord.TextChannel):
            if antes.topic != depois.topic:
                mudancas.append(f"Tópico alterado: {(antes.topic or 'vazio')[:200]} → {(depois.topic or 'vazio')[:200]}")
            if antes.slowmode_delay != depois.slowmode_delay:
                mudancas.append(f"Modo lento: {antes.slowmode_delay}s → {depois.slowmode_delay}s")
            if antes.nsfw != depois.nsfw:
                mudancas.append(f"NSFW: {antes.nsfw} → {depois.nsfw}")
        if not mudancas:
            return
        canal = await self._canal_logs(depois.guild)
        if not canal:
            return
        embed = discord.Embed(
            title="Canal atualizado",
            description=f"Canal: {depois.name} ({depois.id})\n" + "\n".join(mudancas),
            color=0xFEE75C,
        )
        await self._enviar_log(canal, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        canal = await self._canal_logs(role.guild)
        if canal:
            await self._enviar_log(canal, discord.Embed(
                title="Cargo criado",
                description=f"Cargo: {role.name} ({role.id})\nCor: {role.color}",
                color=0x57F287,
            ))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        canal = await self._canal_logs(role.guild)
        if canal:
            await self._enviar_log(canal, discord.Embed(
                title="Cargo excluído",
                description=f"Cargo: {role.name} ({role.id})",
                color=0xED4245,
            ))

    @commands.Cog.listener()
    async def on_guild_role_update(self, antes: discord.Role, depois: discord.Role):
        mudancas = []
        if antes.name != depois.name:
            mudancas.append(f"Nome: {antes.name} → {depois.name}")
        if antes.color != depois.color:
            mudancas.append(f"Cor: {antes.color} → {depois.color}")
        if antes.hoist != depois.hoist:
            mudancas.append(f"Separado na lista: {antes.hoist} → {depois.hoist}")
        if antes.mentionable != depois.mentionable:
            mudancas.append(f"Mencionável: {antes.mentionable} → {depois.mentionable}")
        if antes.permissions != depois.permissions:
            mudancas.append("As permissões do cargo foram alteradas.")
        if not mudancas:
            return
        canal = await self._canal_logs(depois.guild)
        if canal:
            await self._enviar_log(canal, discord.Embed(
                title="Cargo atualizado",
                description=f"Cargo: {depois.name} ({depois.id})\n" + "\n".join(mudancas),
                color=0xFEE75C,
            ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
