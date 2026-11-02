from utils.apresentacao import criar_embed
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils.guia_servidores import (
    GuiaServidoresView,
    CARGO_VISITANTES_ID,
    NOME_CARGO_VISITANTES,
    TAG_ORG_NEMESIS,
)
from utils.storage import carregar
from utils.registro_global import CANAL_REGISTRO_GLOBAL_ID, CATEGORIAS, garantir_topicos, registrar as registrar_global


logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
CANAL_ENTRADAS_ID = 1563995880623841331


class Logs(commands.Cog):
    """Registra eventos do servidor (entradas, saídas, edições e exclusões de mensagem)
    no Fórum central de Registro Global da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._topicos_prontos = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._topicos_prontos:
            return
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            logger.error("Guild NÊMESIS não está em cache; tópicos do Registro Global aguardam conexão.")
            return
        try:
            topicos = await garantir_topicos(guild)
            self._topicos_prontos = len(topicos) == len(CATEGORIAS)
            logger.info("Registro Global pronto: %s/%s tópicos permanentes verificados.", len(topicos), len(CATEGORIAS))
        except Exception:
            logger.exception("Não foi possível provisionar os tópicos do Registro Global.")

    async def _canal_logs(self, guild: discord.Guild):
        """Resolve exclusivamente o Fórum central de registros da NÊMESIS."""
        if guild.id != GUILD_NEMESIS_ID:
            return None
        try:
            canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
            if not isinstance(canal, discord.ForumChannel):
                logger.error("O Registro Global configurado não é um Fórum (%s).", CANAL_REGISTRO_GLOBAL_ID)
                return None
            return canal
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception("Fórum de Registro Global indisponível (guild=%s).", guild.id)
            return None

    async def _enviar_log(self, canal, embed: discord.Embed, view: discord.ui.View | None = None, categoria: str = "membros"):
        """Envia eventos ao tópico fixo; mantém o canal de boas-vindas separado."""
        try:
            if embed.timestamp is None:
                embed.timestamp = datetime.now(timezone.utc)
            if not embed.footer.text:
                embed.set_footer(text="NÊMESIS • Registro Global")
            if isinstance(canal, discord.ForumChannel):
                return await registrar_global(
                    canal.guild, categoria, embed.title or "Registro", embed=embed,
                )
            await canal.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
            return True
        except Exception:
            logger.exception("Falha ao publicar registro (channel=%s).", getattr(canal, "id", "desconhecido"))
            return False

    async def _convidador_do_membro(self, guild_id: int, member_id: int):
        try:
            dados = await carregar("convites_nemesis.json", {})
            servidor = dados.get(str(guild_id), {}) if isinstance(dados, dict) else {}
            historico = servidor.get("_historico", {}) if isinstance(servidor, dict) else {}
            convidador_id = historico.get(str(member_id))
            return int(convidador_id) if convidador_id else None
        except Exception:
            logger.exception("Falha ao consultar convidador (guild=%s, member=%s).", guild_id, member_id)
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != 1563995879981981817:
            return
        canal = member.guild.get_channel(CANAL_ENTRADAS_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(CANAL_ENTRADAS_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.exception(
                    "Canal de boas-vindas indisponível (guild=%s, channel=%s, member=%s).",
                    member.guild.id, CANAL_ENTRADAS_ID, member.id,
                )
                canal = None
        if canal is not None and (
            not isinstance(canal, discord.TextChannel) or canal.guild.id != GUILD_NEMESIS_ID
        ):
            logger.error("Destino de boas-vindas inválido (channel=%s).", CANAL_ENTRADAS_ID)
            canal = None

        # Dá tempo ao rastreador para persistir a atribuição deste evento.
        import asyncio
        await asyncio.sleep(0.8)
        convidador_id = await self._convidador_do_membro(member.guild.id, member.id)
        conta_criada = discord.utils.format_dt(member.created_at, style="R")
        total_membros = member.guild.member_count or 0
        agora = datetime.now(timezone.utc)
        embed = criar_embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOVA PRESENÇA ・✦",
            description=(
                "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "     **UMA NOVA JORNADA COMEÇA**\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"⟡・Seja bem-vindo(a), {member.mention}.\n"
                "Você acaba de entrar na **NÊMESIS** — uma organização de competição, evolução "
                "e comunidade. Explore os canais oficiais, conheça as divisões e participe das atividades."
            ),
            color=0xB3132B,
            timestamp=agora,
        )
        if member.guild.icon:
            embed.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  |  CENTRAL DE INTEGRAÇÃO", icon_url=member.guild.icon.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="◈  IDENTIFICAÇÃO",
            value=f"**Integrante:** {member.mention}\n**Registro:** `{member.id}`\n**Efetivo atual:** `{total_membros:,}`",
            inline=False,
        )
        embed.add_field(
            name="◈  IDENTIDADE DA ORGANIZAÇÃO",
            value=f"**TAG DA ORG:** `{TAG_ORG_NEMESIS}`\n**Cargo inicial:** <@&{CARGO_VISITANTES_ID}> — {NOME_CARGO_VISITANTES}",
            inline=True,
        )
        embed.add_field(
            name="◈  RECRUTAMENTO",
            value=f"**Convidador:** <@{convidador_id}>" if convidador_id else
                  "**Convidador:** Não identificado com segurança.",
            inline=True,
        )
        embed.add_field(
            name="◈  REGISTRO",
            value=f"**Conta criada:** {conta_criada}\n**Entrada:** {discord.utils.format_dt(agora, style='F')}",
            inline=True,
        )
        embed.add_field(
            name="╭・SEU PRIMEIRO PASSO",
            value=(
                "01. **Leia as regras:** conheça as normas antes de participar.\n"
                "02. **Entenda a estrutura:** visite Como funciona e Divisões.\n"
                "03. **Aprenda os sistemas:** abra #Sistemas e selecione um tutorial.\n"
                "04. **Entre em atividade:** acompanhe missões, eventos e progressão.\n"
                "05. **Precisa de ajuda?** acesse Atendimento pelos botões abaixo."
            ),
            inline=False,
        )
        embed.add_field(
            name="✦  SEU PRÓXIMO CAPÍTULO COMEÇA AGORA",
            value="A TAG oficial da organização é **NΞM**. A NÊMESIS reconhece atitude, consistência e espírito competitivo. **Mostre do que você é capaz.**",
            inline=False,
        )
        embed.set_footer(text="NÊMESIS • TAG DA ORG: NΞM • Sistema oficial de integração")
        if canal is not None:
            enviado = await self._enviar_log(canal, embed, view=GuiaServidoresView())
            if enviado:
                logger.info("Mensagem de entrada publicada (guild=%s, member=%s, channel=%s, inviter=%s).",
                            member.guild.id, member.id, canal.id, convidador_id or "desconhecido")
            else:
                logger.error("Falha ao publicar mensagem de entrada (guild=%s, member=%s, channel=%s).",
                             member.guild.id, member.id, canal.id)
        await registrar_global(
            member.guild,
            "entradas",
            "Novo membro na NÊMESIS",
            (
                f"Membro: {member.mention} (`{member.id}`)\n"
                f"Conta criada: {discord.utils.format_dt(member.created_at, style='F')}\n"
                f"Efetivo após entrada: {total_membros}\n"
                f"Convidador: <@{convidador_id}>"
                if convidador_id else
                f"Membro: {member.mention} (`{member.id}`)\n"
                f"Conta criada: {discord.utils.format_dt(member.created_at, style='F')}\n"
                f"Efetivo após entrada: {total_membros}\nConvidador: Não identificado"
            ),
            cor=0x57F287,
        )
        await registrar_global(
            member.guild, "historico_membros", "Entrada no histórico do membro",
            f"Membro: {member} (ID: {member.id})\nEntrada: {discord.utils.format_dt(agora, style='F')}\nConta criada: {discord.utils.format_dt(member.created_at, style='F')}",
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        agora = datetime.now(timezone.utc)
        canal = await self._canal_logs(member.guild)
        if canal:
            embed = criar_embed(
                title="Saída de membro",
                description=f"📤 {member} (ID: {member.id}) saiu da NÊMESIS.",
                color=0xED4245,
                timestamp=agora,
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await self._enviar_log(canal, embed, categoria="entradas")
        await registrar_global(
            member.guild, "historico_membros", "Saída do membro",
            f"Membro: {member} (ID: {member.id})\\nSaída registrada: {discord.utils.format_dt(agora, style='F')}",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        canal = await self._canal_logs(message.guild)
        if not canal or canal.id == message.channel.id:
            return  # evita loop se o canal de logs for o mesmo onde a mensagem foi apagada
        conteudo = message.content or "*(sem texto disponível no cache do Discord)*"
        conteudo = conteudo[:1800]  # protege contra embeds inválidos por conteúdo excessivo
        anexos = "\n".join(
            f"[{anexo.filename}]({anexo.url})" for anexo in message.attachments[:8]
        )
        descricao = (
            f"**Autor:** {message.author.mention} (ID: {message.author.id})\n"
            f"**Canal de origem:** {message.channel.mention} (ID: {message.channel.id})\n"
            f"**ID da mensagem:** {message.id}\n"
            f"**Conteúdo registrado:**\n{conteudo[:1200]}"
        )
        if anexos:
            descricao += f"\n**Anexos:**\n{anexos[:1200]}"
        descricao += (
            "\n\n*Auditoria informativa: o evento de exclusão do Discord não identifica "
            "com segurança quem executou a exclusão. Este listener não apaga mensagens.*"
        )
        embed = criar_embed(
            title="AUDITORIA • MENSAGEM EXCLUÍDA",
            description=descricao[:4000],
            color=0xED4245,
            timestamp=datetime.now(timezone.utc),
        )
        await self._enviar_log(canal, embed, categoria="mensagens")
        if message.attachments:
            await registrar_global(message.guild, "anexos", "Anexos removidos com mensagem", descricao, cor=0xED4245)
        await registrar_global(message.guild, "historico_membros", "Mensagem removida", descricao, cor=0xED4245)

    @commands.Cog.listener()
    async def on_message_edit(self, antes: discord.Message, depois: discord.Message):
        if antes.author.bot or not antes.guild:
            return
        anexos_antes = [anexo.url for anexo in antes.attachments]
        anexos_depois = [anexo.url for anexo in depois.attachments]
        if antes.content == depois.content and anexos_antes == anexos_depois:
            return
        embed = criar_embed(
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
            await self._enviar_log(canal, embed, categoria="mensagens")
            if anexos_antes != anexos_depois:
                await registrar_global(antes.guild, "anexos", "Anexos de mensagem alterados", embed.description or "Anexos alterados.", cor=0xFEE75C)
            await registrar_global(antes.guild, "historico_membros", "Mensagem editada", embed.description or "Mensagem editada.", cor=0xFEE75C)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = criar_embed(description=f"🔨 {user.mention} (`{user}`) foi banido do servidor.", color=0xED4245)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._enviar_log(canal, embed, categoria="moderacao")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = criar_embed(description=f"⚖️ {user.mention} (`{user}`) foi desbanido do servidor.", color=0x57F287)
        await self._enviar_log(canal, embed, categoria="moderacao")

    @commands.Cog.listener()
    async def on_member_update(self, antes: discord.Member, depois: discord.Member):
        canal = await self._canal_logs(depois.guild)
        if not canal:
            return

        if antes.nick != depois.nick:
            embed = criar_embed(
                title="Apelido alterado",
                description=(
                    f"**Membro:** {depois.mention} ({depois.id})\n"
                    f"**Antes:** {antes.nick or antes.name}\n"
                    f"**Depois:** {depois.nick or depois.name}"
                ),
                color=0xFEE75C,
            )
            await self._enviar_log(canal, embed, categoria="historico_membros")
            await registrar_global(depois.guild, "historico_membros", "Apelido alterado", embed.description or "Apelido alterado.", cor=0xFEE75C)

        ids_antes = {cargo.id: cargo for cargo in antes.roles if not cargo.is_default()}
        ids_depois = {cargo.id: cargo for cargo in depois.roles if not cargo.is_default()}
        ganhos = [cargo for cargo_id, cargo in ids_depois.items() if cargo_id not in ids_antes]
        perdidos = [cargo for cargo_id, cargo in ids_antes.items() if cargo_id not in ids_depois]
        if ganhos or perdidos:
            embed = criar_embed(
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
            await self._enviar_log(canal, embed, categoria="cargos")
            await registrar_global(depois.guild, "historico_membros", "Cargos do membro alterados", embed.description or "Cargos alterados.", cor=0xB3132B)

        # Compatível com versões de discord.py em que o atributo não está
        # disponível no objeto Member. A comparação não pode derrubar o listener.
        timeout_antes = getattr(antes, "communication_disabled_until", None)
        timeout_depois = getattr(depois, "communication_disabled_until", None)
        if timeout_antes != timeout_depois:
            embed = criar_embed(
                title="Timeout alterado",
                description=f"**Membro:** {depois.mention} ({depois.id})",
                color=0xFEE75C,
            )
            embed.add_field(
                name="Antes",
                value=discord.utils.format_dt(timeout_antes, style="F")
                if timeout_antes else "Sem timeout",
                inline=True,
            )
            embed.add_field(
                name="Depois",
                value=discord.utils.format_dt(timeout_depois, style="F")
                if timeout_depois else "Sem timeout",
                inline=True,
            )
            await self._enviar_log(canal, embed, categoria="moderacao")
            await registrar_global(depois.guild, "historico_membros", "Timeout alterado", embed.description or "Timeout alterado.", cor=0xFEE75C)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await self._enviar_log(canal, criar_embed(description=f"📁 Canal criado: **{channel.name}** ({channel.type}).", color=0x57F287), categoria="administracao")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        canal = await self._canal_logs(channel.guild)
        if not canal:
            return
        await self._enviar_log(canal, criar_embed(description=f"🗑️ Canal apagado: **{channel.name}** ({channel.type}).", color=0xED4245), categoria="administracao")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        if antes.channel is None and depois.channel is not None:
            detalhe = f"{member.mention} entrou no canal de voz **{depois.channel.name}** (`{depois.channel.id}`)."
            await self._enviar_log(canal, criar_embed(description=f"🔊 {detalhe}", color=0x57F287), categoria="voz")
            await registrar_global(member.guild, "historico_membros", "Entrada em chamada", detalhe, cor=0x57F287)
        elif antes.channel is not None and depois.channel is None:
            detalhe = f"{member.mention} saiu do canal de voz **{antes.channel.name}** (`{antes.channel.id}`)."
            await self._enviar_log(canal, criar_embed(description=f"🔇 {detalhe}", color=0xED4245), categoria="voz")
            await registrar_global(member.guild, "historico_membros", "Saída de chamada", detalhe, cor=0xED4245)
        elif antes.channel != depois.channel:
            detalhe = f"{member.mention} mudou de **{antes.channel.name}** para **{depois.channel.name}**."
            await self._enviar_log(canal, criar_embed(description=f"🔀 {detalhe}", color=0xFEE75C), categoria="voz")
            await registrar_global(member.guild, "historico_membros", "Movimentação em chamada", detalhe, cor=0xFEE75C)


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
        embed = criar_embed(
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
        await self._enviar_log(canal, embed, categoria="mensagens")

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
        if antes.overwrites != depois.overwrites:
            mudancas.append("As permissões e sobrescritas de acesso do canal foram alteradas.")
        if not mudancas:
            return
        canal = await self._canal_logs(depois.guild)
        if not canal:
            return
        embed = criar_embed(
            title="Canal atualizado",
            description=f"Canal: {depois.name} ({depois.id})\n" + "\n".join(mudancas),
            color=0xFEE75C,
        )
        await self._enviar_log(canal, embed, categoria="administracao")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        canal = await self._canal_logs(role.guild)
        if canal:
            await self._enviar_log(canal, criar_embed(
                title="Cargo criado",
                description=f"Cargo: {role.name} ({role.id})\nCor: {role.color}",
                color=0x57F287,
            ), categoria="administracao")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        canal = await self._canal_logs(role.guild)
        if canal:
            await self._enviar_log(canal, criar_embed(
                title="Cargo excluído",
                description=f"Cargo: {role.name} ({role.id})",
                color=0xED4245,
            ), categoria="administracao")

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
            await self._enviar_log(canal, criar_embed(
                title="Cargo atualizado",
                description=f"Cargo: {depois.name} ({depois.id})\n" + "\n".join(mudancas),
                color=0xFEE75C,
            ), categoria="administracao")


    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.guild.id != GUILD_NEMESIS_ID or thread.parent_id == CANAL_REGISTRO_GLOBAL_ID:
            return
        await registrar_global(
            thread.guild, "administracao", "Tópico criado",
            f"Tópico: **{thread.name}** (`{thread.id}`)\nCanal pai: <#{thread.parent_id}>",
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if thread.guild.id != GUILD_NEMESIS_ID or thread.parent_id == CANAL_REGISTRO_GLOBAL_ID:
            return
        await registrar_global(
            thread.guild, "administracao", "Tópico excluído",
            f"Tópico: **{thread.name}** (`{thread.id}`)\nCanal pai: `{thread.parent_id}`",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_thread_update(self, antes: discord.Thread, depois: discord.Thread):
        if depois.guild.id != GUILD_NEMESIS_ID or depois.parent_id == CANAL_REGISTRO_GLOBAL_ID:
            return
        mudancas = []
        if antes.name != depois.name:
            mudancas.append(f"Nome: {antes.name} → {depois.name}")
        if antes.archived != depois.archived:
            mudancas.append(f"Arquivado: {antes.archived} → {depois.archived}")
        if antes.locked != depois.locked:
            mudancas.append(f"Bloqueado: {antes.locked} → {depois.locked}")
        if mudancas:
            await registrar_global(
                depois.guild, "administracao", "Tópico atualizado",
                f"Tópico: **{depois.name}** (`{depois.id}`)\n" + "\n".join(mudancas),
                cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            invite.guild, "convites", "Convite criado",
            f"Código: `{invite.code}`\nCanal: {invite.channel.mention if invite.channel else 'Não identificado'}\n"
            f"Criado por: {invite.inviter.mention if invite.inviter else 'Não identificado'}\n"
            f"Usos máximos: {invite.max_uses or 'Ilimitado'}",
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            invite.guild, "convites", "Convite removido",
            f"Código: `{invite.code}`\nCanal: {invite.channel.mention if invite.channel else 'Não identificado'}",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if channel.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            channel.guild, "seguranca", "Webhooks atualizados",
            f"Canal afetado: {channel.mention if hasattr(channel, 'mention') else channel.name} (`{channel.id}`)\n"
            "O Discord notificou uma alteração na configuração de webhooks deste canal.",
            cor=0xFEE75C,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild.id != GUILD_NEMESIS_ID:
            return
        descricao = (
            f"Evento: **{event.name}** (`{event.id}`)\n"
            f"Início: {discord.utils.format_dt(event.start_time, style='F')}\n"
            f"Término: {discord.utils.format_dt(event.end_time, style='F') if event.end_time else 'Não definido'}\n"
            f"Criado por: <@{event.creator_id}>" if event.creator_id else
            f"Evento: **{event.name}** (`{event.id}`)\n"
            f"Início: {discord.utils.format_dt(event.start_time, style='F')}\n"
            f"Término: {discord.utils.format_dt(event.end_time, style='F') if event.end_time else 'Não definido'}"
        )
        await registrar_global(
            event.guild, "eventos", "Evento agendado criado", descricao,
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        if event.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            event.guild, "eventos", "Evento agendado removido",
            f"Evento: **{event.name}** (`{event.id}`)\nStatus final: {event.status}",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, antes: discord.ScheduledEvent, depois: discord.ScheduledEvent):
        if depois.guild.id != GUILD_NEMESIS_ID:
            return
        mudancas = []
        for atributo, rotulo in (("name", "Nome"), ("description", "Descrição"), ("start_time", "Início"), ("end_time", "Término"), ("status", "Status"), ("location", "Local")):
            valor_antes = getattr(antes, atributo, None)
            valor_depois = getattr(depois, atributo, None)
            if valor_antes != valor_depois:
                mudancas.append(f"{rotulo}: {valor_antes} → {valor_depois}")
        if mudancas:
            await registrar_global(
                depois.guild, "eventos", "Evento agendado atualizado",
                f"Evento: **{depois.name}** (`{depois.id}`)\n" + "\n".join(mudancas),
                cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_update(self, antes: discord.Guild, depois: discord.Guild):
        if depois.id != GUILD_NEMESIS_ID:
            return
        mudancas = []
        for atributo, rotulo in (("name", "Nome"), ("description", "Descrição"), ("verification_level", "Verificação"), ("explicit_content_filter", "Filtro de conteúdo"), ("default_notifications", "Notificações padrão"), ("afk_timeout", "Timeout AFK")):
            if getattr(antes, atributo, None) != getattr(depois, atributo, None):
                mudancas.append(f"{rotulo}: {getattr(antes, atributo, None)} → {getattr(depois, atributo, None)}")
        if mudancas:
            await registrar_global(
                depois, "administracao", "Configurações do servidor alteradas",
                "\n".join(mudancas), cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, antes, depois):
        if guild.id != GUILD_NEMESIS_ID:
            return
        ids_antes = {item.id: item for item in antes}
        ids_depois = {item.id: item for item in depois}
        criados = [item.name for key, item in ids_depois.items() if key not in ids_antes]
        removidos = [item.name for key, item in ids_antes.items() if key not in ids_depois]
        if criados or removidos:
            await registrar_global(
                guild, "administracao", "Emojis do servidor alterados",
                f"Criados: {', '.join(criados) or 'Nenhum'}\nRemovidos: {', '.join(removidos) or 'Nenhum'}",
                cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, antes, depois):
        if guild.id != GUILD_NEMESIS_ID:
            return
        ids_antes = {item.id: item for item in antes}
        ids_depois = {item.id: item for item in depois}
        criados = [item.name for key, item in ids_depois.items() if key not in ids_antes]
        removidos = [item.name for key, item in ids_antes.items() if key not in ids_depois]
        if criados or removidos:
            await registrar_global(
                guild, "administracao", "Figurinhas do servidor alteradas",
                f"Criadas: {', '.join(criados) or 'Nenhuma'}\nRemovidas: {', '.join(removidos) or 'Nenhuma'}",
                cor=0xFEE75C,
            )



async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
