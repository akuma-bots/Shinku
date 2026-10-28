import time
import io
import asyncio
import logging
import unicodedata
import discord
from discord.ext import commands, tasks
from utils.apresentacao import criar_embed
from utils.storage import carregar_config
from utils.guild_config import get_config, set_config
from utils import tickets


log = logging.getLogger(__name__)


async def _preparar_resposta_interacao(interaction: discord.Interaction) -> None:
    """Adia a resposta do componente sem tentar reconhecer a interação duas vezes."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)


CANAIS_ESCALADOS = set()        # tickets já entregues para atendimento humano
ULTIMA_ATIVIDADE = {}           # channel_id -> timestamp da última mensagem
CANAIS_FECHANDO = set()         # evita fechar o mesmo canal duas vezes ao mesmo tempo
ABERTURA_TICKET_LOCK = asyncio.Lock()  # serializa abertura para o mesmo processo

FRASES_FECHAR = [
    "fechar o ticket",
    "fechar ticket",
    "encerrar o ticket",
    "encerrar ticket",
]

TEMPO_INATIVIDADE_SEGUNDOS = 10 * 60  # 10 minutos

CUSTOM_ID_SELECT = "ticket:abrir_select"
TICKET_PAINEL_CANAL_ID = 1545836351596011570

TITULO_PADRAO = "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE ATENDIMENTO ・✦"
DESCRICAO_PADRAO = (
    "Precisa de ajuda? Selecione abaixo a categoria que melhor representa "
    "sua solicitação para abrir um atendimento privado com a equipe NÊMESIS."
)


def _normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return texto


def _resolver_problema(mensagem: str, base: list):
    texto = _normalizar(mensagem)

    melhor_entrada = None
    melhor_pontuacao = 0

    for entrada in base:
        pontuacao = 0

        for frase in entrada["palavras_chave"]:
            palavras = _normalizar(frase).split()

            if all(p in texto for p in palavras):
                pontuacao += len(palavras)

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_entrada = entrada

    return melhor_entrada if melhor_pontuacao > 0 else None


async def fechar_canal_ticket(
    canal: discord.TextChannel,
    motivo: str,
    delay: int = 5,
    fechado_por_id: int | None = None,
):
    if canal.id in CANAIS_FECHANDO:
        return

    CANAIS_FECHANDO.add(canal.id)

    ULTIMA_ATIVIDADE.pop(canal.id, None)
    CANAIS_ESCALADOS.discard(canal.id)

    try:
        # Registra o fechamento no armazenamento compartilhado
        ticket = await tickets.get_ticket_por_canal(canal.guild.id, canal.id)

        if ticket:
            await tickets.fechar_ticket(
                canal.guild.id,
                ticket["id"],
                fechado_por_id=fechado_por_id,
                motivo=motivo,
            )
            ticket = await tickets.get_ticket(canal.guild.id, ticket["id"]) or ticket
            await _publicar_historico_ticket(canal, ticket, motivo, fechado_por_id)

        if ticket:
            dono = canal.guild.get_member(int(ticket.get("usuario_id") or 0))
            if dono:
                try:
                    embed = criar_embed(
                        "✦・ NÊMESIS — AVALIAÇÃO DE ATENDIMENTO ・✦",
                        f"Seu atendimento #{ticket.get('id', '—')} foi encerrado.\n\nSua avaliação é necessária para concluir o atendimento. Escolha uma nota de 1 a 5 abaixo.",
                        rodape="NÊMESIS • Central de atendimento",
                    )
                    await dono.send(embed=embed, view=AvaliacaoTicketView(
                        canal.guild.id, str(ticket["id"]), int(ticket.get("usuario_id") or 0),
                        int(ticket.get("atendido_por_id") or 0),
                    ))
                    await tickets.atualizar_ticket(canal.guild.id, ticket["id"], avaliacao_solicitada=True)
                except discord.Forbidden:
                    logging.info("Não foi possível enviar a avaliação por DM; usuário %s.", ticket.get("usuario_id"))
                except discord.HTTPException:
                    logging.exception("Falha ao enviar prompt de avaliação do ticket.")

        await canal.send(f"🔒 Fechando este ticket em {delay}s. Motivo: {motivo}")
        await asyncio.sleep(delay)
        await canal.delete(reason=motivo)

    except discord.NotFound:
        # Mesmo que o canal já tenha sido apagado, tenta manter
        # o registro persistente como fechado.
        try:
            ticket = await tickets.get_ticket_por_canal(canal.guild.id, canal.id)

            if ticket:
                await tickets.fechar_ticket(
                    canal.guild.id,
                    ticket["id"],
                    fechado_por_id=fechado_por_id,
                    motivo=motivo,
                )
        except Exception:
            pass

    except Exception:
        raise

    finally:
        CANAIS_FECHANDO.discard(canal.id)


async def _montar_select(guild_id: int) -> discord.ui.View:
    tipos = await tickets.get_tipos(guild_id)
    if not tipos:
        # O Discord não aceita um select vazio; recupera as categorias padrão.
        tipos = list(tickets.TIPOS_PADRAO)

    # Emojis decorativos (◈, ✦, ◇ etc.) não são aceitos como emojis
    # de SelectOption pelo Discord. Usa apenas emojis Unicode válidos.
    emojis_validos = {
        "recrutamento": "⚔️",
        "hierarquia_divisoes": "🎖️",
        "conflitos_denuncias": "⚖️",
        "guerras_desafios": "🎯",
        "suporte_comunidade": "🛟",
        "aliancas": "🤝",
        "eventos_atividades": "🎉",
        "sugestoes_projetos": "💡",
    }
    options = [
        discord.SelectOption(
            label=str(t.get("label") or "Atendimento")[:100],
            value=str(t.get("valor") or "outro")[:100],
            description=str(t.get("descricao") or "Solicitação de atendimento.")[:100],
            emoji=(
                t.get("emoji")
                if t.get("emoji") in {"⚔️", "🎖️", "⚖️", "🎯", "🛟", "🤝", "🎉", "💡"}
                else emojis_validos.get(t["valor"])
            ),
        )
        for t in tipos[:25]
    ]

    select = discord.ui.Select(
        placeholder="Selecione o tipo de atendimento",
        options=options,
        custom_id=CUSTOM_ID_SELECT,
    )

    view = discord.ui.View(timeout=None)
    view.add_item(select)

    return view


async def _montar_embed_painel(guild_id: int) -> discord.Embed:
    config = await get_config(guild_id)
    descricao = config.get("ticket_painel_descricao") or DESCRICAO_PADRAO

    # Migra o texto padrão antigo sem sobrescrever descrições personalizadas.
    if (
        descricao.startswith("A Central de Atendimento é o canal oficial para tratar de assuntos da")
        and "◈ ORIENTAÇÕES ◈" in descricao
    ):
        descricao = DESCRICAO_PADRAO

    embed = criar_embed(
        config.get("ticket_painel_titulo") or TITULO_PADRAO,
        descricao,
        rodape="NÊMESIS • Suporte oficial",
    )
    embed.add_field(
        name="◈ ANTES DE ABRIR",
        value=(
            "➜ Escolha a categoria correta.\n"
            "➜ Explique o caso com clareza e inclua provas, se necessário.\n"
            "➜ Não abra tickets duplicados nem marque a equipe repetidamente."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔒 PRIVACIDADE",
        value=(
            "O ticket é privado e visível apenas para você e a equipe autorizada. "
            "Denúncias e informações sensíveis devem ser tratadas dentro do atendimento."
        ),
        inline=False,
    )
    embed.color = 0x8B0000

    banner_url = config.get("ticket_painel_banner_url")
    if banner_url:
        embed.set_image(url=banner_url)

    return embed


CANAL_AVALIACOES_TICKET_ID = 1545835885063438487

CANAL_HISTORICO_TICKETS_ID = 1563995882540498997

async def _publicar_historico_ticket(canal, ticket, motivo, fechado_por_id):
    destino = canal.guild.get_channel(CANAL_HISTORICO_TICKETS_ID)
    if destino is None:
        try:
            destino = await canal.guild.fetch_channel(CANAL_HISTORICO_TICKETS_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logging.error("Canal de histórico de tickets indisponível: %s", CANAL_HISTORICO_TICKETS_ID)
            return
    if not callable(getattr(destino, "send", None)):
        return
    usuario_id = int(ticket.get("usuario_id") or 0)
    atendente_id = int(ticket.get("atendido_por_id") or 0)
    registros = await tickets.listar_tickets(canal.guild.id)
    atendidos = [t for t in registros if isinstance(t, dict) and str(t.get("atendido_por_id") or "") == str(atendente_id) and t.get("status") == "fechado"] if atendente_id else []
    notas = [int(t["avaliacao"]) for t in atendidos if str(t.get("avaliacao", "")).isdigit() and 1 <= int(t["avaliacao"]) <= 5]
    media = sum(notas) / len(notas) if notas else None
    try:
        mensagens = [m async for m in canal.history(limit=None, oldest_first=True)]
    except (discord.Forbidden, discord.HTTPException):
        logging.exception("Não foi possível ler o histórico do ticket %s", ticket.get("id"))
        mensagens = []
    linhas = [
        f"TRANSCRIÇÃO DO TICKET #{ticket.get('id', '—')}",
        f"Servidor: {canal.guild.name} ({canal.guild.id})",
        f"Canal: {canal.name} ({canal.id})",
        f"Categoria: {ticket.get('tipo', 'Não informada')}",
        f"Cliente: {usuario_id}",
        f"Responsável: {atendente_id or 'Não atribuído'}",
        f"Tickets encerrados pelo responsável: {len(atendidos)}",
        f"Média do responsável: {media:.2f}/5 ({len(notas)} avaliação(ões))" if media is not None else "Média do responsável: ainda sem avaliações",
        f"Fechado por: {fechado_por_id or 'sistema'}",
        f"Motivo: {motivo}",
        "",
        "================ CONVERSA COMPLETA ================",
        "",
    ]
    for msg in mensagens:
        linhas.append(f"[{discord.utils.format_dt(msg.created_at, style='F')}] {msg.author} (ID {msg.author.id}):")
        linhas.append(msg.content or "[Sem texto]")
        for anexo in msg.attachments:
            linhas.append(f"Anexo: {anexo.filename} — {anexo.url}")
        for emb in msg.embeds:
            if emb.title: linhas.append(f"[Embed] {emb.title}")
            if emb.description: linhas.append(f"[Embed] {emb.description}")
            for campo in emb.fields: linhas.append(f"[Embed: {campo.name}] {campo.value}")
        linhas.append("")
    texto = "\n".join(linhas)
    resumo = criar_embed(f"📁 Histórico do Ticket #{ticket.get('id', '—')}", "Transcrição preservada antes da exclusão do canal.", rodape="NÊMESIS • Auditoria de atendimento")
    resumo.add_field(name="Cliente", value=f"<@{usuario_id}> · ID {usuario_id}", inline=True)
    resumo.add_field(name="Responsável", value=f"<@{atendente_id}> · ID {atendente_id}" if atendente_id else "Não atribuído", inline=True)
    resumo.add_field(name="Tickets encerrados", value=str(len(atendidos)), inline=True)
    resumo.add_field(name="Média de estrelas", value=f"{media:.2f}/5 ⭐" if media is not None else "Sem avaliações", inline=True)
    resumo.add_field(name="Mensagens preservadas", value=str(len(mensagens)), inline=True)
    resumo.add_field(name="Motivo", value=str(motivo)[:1024], inline=False)
    try:
        await destino.send(embed=resumo, allowed_mentions=discord.AllowedMentions.none())
        dados = texto.encode("utf-8")
        if len(dados) <= 7_000_000:
            await destino.send(file=discord.File(io.BytesIO(dados), filename=f"ticket-{ticket.get('id', 'historico')}.txt"), allowed_mentions=discord.AllowedMentions.none())
        else:
            parte = 1
            bloco = ""
            for linha in linhas:
                while len(linha) > 1800:
                    if bloco:
                        await destino.send(f"Transcrição #{ticket.get('id')} — parte {parte}\n{bloco}", allowed_mentions=discord.AllowedMentions.none())
                        parte += 1
                        bloco = ""
                    await destino.send(f"Transcrição #{ticket.get('id')} — parte {parte}\n{linha[:1800]}", allowed_mentions=discord.AllowedMentions.none())
                    parte += 1
                    linha = linha[1800:]
                candidato = (bloco + "\n" + linha).strip()
                if len(candidato) > 1800:
                    await destino.send(f"Transcrição #{ticket.get('id')} — parte {parte}\n{bloco}", allowed_mentions=discord.AllowedMentions.none())
                    parte += 1
                    bloco = linha
                else:
                    bloco = candidato
            if bloco:
                await destino.send(f"Transcrição #{ticket.get('id')} — parte {parte}\n{bloco}", allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        logging.exception("Falha ao publicar a transcrição do ticket %s", ticket.get("id"))


async def _estatisticas_atendente(guild_id: int, atendente_id: int) -> tuple[int, float | None]:
    registros = await tickets.listar_tickets(guild_id)
    atendidos = [t for t in registros if isinstance(t, dict) and str(t.get("atendido_por_id") or "") == str(atendente_id) and t.get("status") == "fechado"]
    notas = [int(t["avaliacao"]) for t in atendidos if str(t.get("avaliacao", "")).isdigit() and 1 <= int(t["avaliacao"]) <= 5]
    return len(atendidos), (sum(notas) / len(notas) if notas else None)


class FeedbackTicketModal(discord.ui.Modal):
    def __init__(self, guild_id: int, ticket_id: str, owner_id: int, atendente_id: int, nota: int):
        super().__init__(title=f"Avaliar atendimento — {nota}/5", custom_id=f"ticket:feedback:{ticket_id}")
        self.guild_id, self.ticket_id, self.owner_id, self.atendente_id, self.nota = guild_id, ticket_id, owner_id, atendente_id, nota
        self.comentario = discord.ui.TextInput(label="Comentário (opcional)", placeholder="Conte como foi o atendimento ou o que podemos melhorar.", style=discord.TextStyle.paragraph, required=False, max_length=1000)
        self.add_item(self.comentario)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ticket = await tickets.get_ticket(self.guild_id, self.ticket_id)
        if not ticket or ticket.get("status") != "fechado":
            await interaction.followup.send("Este ticket não foi encontrado ou ainda não foi encerrado.", ephemeral=True)
            return
        if str(ticket.get("usuario_id")) != str(self.owner_id) or ticket.get("avaliacao") is not None:
            await interaction.followup.send("Esta avaliação já foi enviada ou não pertence a este atendimento.", ephemeral=True)
            return
        comentario = str(self.comentario.value or "").strip()
        atualizado = await tickets.atualizar_ticket(self.guild_id, self.ticket_id, avaliacao=self.nota, feedback=comentario, avaliado_em=time.time())
        if not atualizado:
            await interaction.followup.send("Não consegui salvar sua avaliação. Tente novamente.", ephemeral=True)
            return
        guild = interaction.client.get_guild(self.guild_id)
        canal = guild.get_channel(CANAL_AVALIACOES_TICKET_ID) if guild else None
        if canal is None and guild:
            try:
                canal = await guild.fetch_channel(CANAL_AVALIACOES_TICKET_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal = None
        total, media = await _estatisticas_atendente(self.guild_id, self.atendente_id) if self.atendente_id else (0, None)
        rotulo = {5: "Excelente", 4: "Muito bom", 3: "Bom", 2: "Regular", 1: "Ruim"}[self.nota]
        media_texto = f"{media:.2f}/5 ⭐" if media is not None else "Ainda sem avaliações"
        if canal is not None and callable(getattr(canal, "send", None)):
            embed = criar_embed("✦・ NÊMESIS — AVALIAÇÃO DE ATENDIMENTO ・✦", f"Ticket #{self.ticket_id} • avaliação verificada", rodape="Central de atendimento NÊMESIS")
            embed.add_field(name="Nota", value=f"{self.nota}/5 — {rotulo}\n{'⭐' * self.nota}", inline=True)
            embed.add_field(name="Cliente", value=f"<@{self.owner_id}> · ID {self.owner_id}", inline=True)
            embed.add_field(name="Responsável", value=f"<@{self.atendente_id}> · ID {self.atendente_id}" if self.atendente_id else "Não identificado", inline=True)
            embed.add_field(name="Feedback", value=comentario[:1024] if comentario else "O cliente não deixou comentário.", inline=False)
            embed.add_field(name="Tickets encerrados pelo responsável", value=str(total), inline=True)
            embed.add_field(name="Média atual do responsável", value=media_texto, inline=True)
            embed.add_field(name="Avaliado em", value=discord.utils.format_dt(discord.utils.utcnow(), style="F"), inline=False)
            try:
                await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                logging.exception("Avaliação do ticket %s salva, mas não publicada.", self.ticket_id)
        await interaction.followup.send(f"Obrigado pelo feedback! Sua avaliação foi registrada: {self.nota}/5 — {rotulo}.", ephemeral=True)


class AvaliacaoTicketView(discord.ui.View):
    def __init__(self, guild_id: int, ticket_id: str, owner_id: int, atendente_id: int):
        super().__init__(timeout=None)
        self.guild_id, self.ticket_id, self.owner_id, self.atendente_id = guild_id, ticket_id, owner_id, atendente_id
        for nota in range(1, 6):
            button = discord.ui.Button(label=f"{nota}/5", emoji="⭐", style=discord.ButtonStyle.primary, custom_id=f"ticket:avaliar:{ticket_id}:{nota}")
            button.callback = self._callback(nota)
            self.add_item(button)

    def _callback(self, nota: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Somente quem abriu o ticket pode avaliá-lo.", ephemeral=True)
                return
            ticket = await tickets.get_ticket(self.guild_id, self.ticket_id)
            if not ticket or ticket.get("status") != "fechado":
                await interaction.response.send_message("Este ticket não foi encontrado ou ainda não foi encerrado.", ephemeral=True)
                return
            if ticket.get("avaliacao") is not None:
                await interaction.response.send_message("Você já avaliou este atendimento.", ephemeral=True)
                return
            await interaction.response.send_modal(FeedbackTicketModal(self.guild_id, self.ticket_id, self.owner_id, self.atendente_id, nota))
        return callback

class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎯 Assumir atendimento",
        style=discord.ButtonStyle.success,
        custom_id="ticket:assumir",
    )
    async def assumir_atendimento(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        canal = interaction.channel
        guild = interaction.guild
        membro = interaction.user

        # Responde imediatamente para evitar expiração da interação durante I/O.
        await _preparar_resposta_interacao(interaction)

        if not guild or not isinstance(canal, discord.TextChannel):
            await interaction.followup.send(
                "Este botão só pode ser usado dentro de um ticket.",
                ephemeral=True,
            )
            return

        info_topic = tickets.parse_topic(canal.topic)
        registro = await tickets.get_ticket_por_canal(guild.id, canal.id)
        if not info_topic or not registro or registro.get("status") != "aberto":
            await interaction.followup.send(
                "Este canal não é um ticket aberto válido.",
                ephemeral=True,
            )
            return

        config = await get_config(guild.id)
        suporte_id = config.get("support_role_id")
        try:
            suporte_id = int(suporte_id) if suporte_id else None
        except (TypeError, ValueError):
            suporte_id = None

        eh_admin = (
            isinstance(membro, discord.Member)
            and (
                membro.guild_permissions.administrator
                or membro.guild_permissions.manage_channels
            )
        )
        cargo_suporte = guild.get_role(suporte_id) if suporte_id else None
        eh_suporte = (
            isinstance(membro, discord.Member)
            and cargo_suporte is not None
            and any(
                cargo.id != guild.default_role.id
                and cargo.position >= cargo_suporte.position
                for cargo in membro.roles
            )
        )
        if not (eh_admin or eh_suporte):
            await interaction.followup.send(
                "Somente a equipe de suporte ou a administração pode assumir este atendimento.",
                ephemeral=True,
            )
            return

        responsavel_atual = registro.get("atendido_por_id")
        if responsavel_atual:
            if str(responsavel_atual) == str(membro.id):
                await interaction.followup.send(
                    "Você já é o responsável por este ticket.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"Este ticket já está sob responsabilidade de <@{responsavel_atual}>. "
                    "Somente a administração pode intervir.",
                    ephemeral=True,
                )
            return

        # Atribuição persistente antes de restringir permissões no canal.
        atualizado = await tickets.registrar_atendimento(
            guild.id,
            registro["id"],
            membro.id,
        )
        if not atualizado:
            await interaction.followup.send(
                "Não consegui registrar a responsabilidade. Tente novamente.",
                ephemeral=True,
            )
            return

        # Bloqueia a equipe comum de enviar mensagens; a pessoa responsável e
        # cargos administrativos recebem permissão explícita para continuar.
        try:
            # Consolida as alterações num único PATCH do canal. Fazer um
            # set_permissions por cargo gera dezenas de pedidos e pode causar 429.
            overwrites = dict(canal.overwrites)
            for cargo in guild.roles:
                if cargo.is_default():
                    continue
                if cargo_suporte and cargo.position >= cargo_suporte.position:
                    atual = overwrites.get(cargo, discord.PermissionOverwrite())
                    atual.view_channel = True
                    atual.send_messages = False
                    atual.read_message_history = True
                    overwrites[cargo] = atual
                if cargo.permissions.administrator or cargo.permissions.manage_channels:
                    overwrites[cargo] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True,
                        manage_channels=True,
                    )

            overwrites[membro] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=eh_admin,
            )
            await canal.edit(
                overwrites=overwrites,
                reason=f"Ticket assumido por {membro} ({membro.id})",
            )
        except (discord.Forbidden, discord.HTTPException):
            # Evita deixar uma atribuição aparentemente concluída sem bloqueio.
            await tickets.remover_responsavel_atendimento(
                guild.id,
                registro["id"],
            )
            await interaction.followup.send(
                "Não consegui aplicar as permissões de responsável. Verifique as permissões do bot.",
                ephemeral=True,
            )
            return

        button.label = f"Responsável: {membro.display_name}"[:80]
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.warning("Não foi possível atualizar os botões do ticket %s após atribuir atendimento.", canal.id)
        await interaction.followup.send(
            f"✅ Você agora é responsável por {canal.mention}. "
            "A equipe comum não pode intervir; a administração continua com acesso.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="🔒 Fechar Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="fechar_ticket_btn",
    )
    async def fechar_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        canal = interaction.channel
        guild = interaction.guild
        membro = interaction.user

        # O fechamento executa operações de armazenamento e exclusão de canal.
        # Adia a resposta para não deixar a interação expirar após 3 segundos.
        await _preparar_resposta_interacao(interaction)

        if not guild or not isinstance(canal, discord.TextChannel):
            await interaction.followup.send(
                "Este botão só pode ser usado dentro de um ticket do servidor.",
                ephemeral=True,
            )
            return

        info_topic = tickets.parse_topic(canal.topic)
        registro = await tickets.get_ticket_por_canal(guild.id, canal.id)
        if (
            not info_topic
            or not registro
            or registro.get("status") != "aberto"
            or str(registro.get("usuario_id")) != str(info_topic.get("owner_id"))
        ):
            await interaction.followup.send(
                "Este canal não é um ticket aberto válido.",
                ephemeral=True,
            )
            return

        config = await get_config(guild.id)
        suporte_id = config.get("support_role_id")
        try:
            suporte_id = int(suporte_id) if suporte_id else None
        except (TypeError, ValueError):
            suporte_id = None

        cargo_suporte = guild.get_role(suporte_id) if suporte_id else None
        eh_suporte = (
            isinstance(membro, discord.Member)
            and cargo_suporte is not None
            and any(
                cargo.id != guild.default_role.id
                and cargo.position >= cargo_suporte.position
                for cargo in membro.roles
            )
        )
        eh_dono = str(membro.id) == str(registro.get("usuario_id"))
        eh_admin = (
            isinstance(membro, discord.Member)
            and (
                membro.guild_permissions.administrator
                or membro.guild_permissions.manage_channels
            )
        )
        responsavel_id = registro.get("atendido_por_id")
        bloqueado_por_responsavel = (
            responsavel_id
            and str(membro.id) != str(responsavel_id)
            and not eh_admin
            and not eh_dono
        )

        if bloqueado_por_responsavel or not (eh_dono or eh_suporte or eh_admin):
            await interaction.followup.send(
                "Somente o dono deste ticket ou a equipe autorizada pode fechá-lo.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "Fechando o ticket...",
            ephemeral=True,
        )

        await fechar_canal_ticket(
            canal,
            f"Fechamento autorizado pelo usuário {membro.id}.",
            delay=5,
            fechado_por_id=membro.id,
        )


class Tickets(commands.Cog):
    """
    Sistema de tickets por categoria.

    O painel mostra um menu suspenso configurável com /ticket-tipo-*.
    Cada opção cria um canal já identificado pelo tipo escolhido.

    Os tickets são persistidos em tickets.json através de utils.tickets, permitindo que o próprio bot mantenha:
    - tickets abertos;
    - tickets fechados;
    - usuário;
    - tipo;
    - canal;
    - atendente;
    - datas;
    - motivo do fechamento.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.base_conhecimento = carregar_config(
            "knowledge_base.json"
        )["entradas"]

        bot.add_view(FecharTicketView())

        self.verificar_inatividade.start()
        self.verificar_painel_permanente.start()

    def cog_unload(self):
        self.verificar_inatividade.cancel()
        self.verificar_painel_permanente.cancel()

    async def _criar_canal_ticket(
        self,
        guild: discord.Guild,
        user: discord.Member,
        tipo: dict,
    ) -> discord.TextChannel:

        config = await get_config(guild.id)

        categoria_id = config["ticket_category_id"]

        categoria = (
            guild.get_channel(categoria_id)
            if categoria_id
            else None
        )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
            ),
        }

        cargo_suporte_id = config["support_role_id"]

        cargo_suporte = (
            guild.get_role(cargo_suporte_id)
            if cargo_suporte_id
            else None
        )

        if cargo_suporte:
            # Equipe de suporte e cargos superiores recebem acesso inicial.
            for cargo in guild.roles:
                if cargo.is_default() or cargo.position < cargo_suporte.position:
                    continue
                overwrites[cargo] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        # Cargos administrativos devem continuar podendo intervir mesmo após
        # o ticket ser assumido, inclusive se estiverem abaixo do cargo suporte.
        for cargo in guild.roles:
            if cargo.is_default():
                continue
            if cargo.permissions.administrator or cargo.permissions.manage_channels:
                overwrites[cargo] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                    manage_channels=True,
                )

        nome_canal = f"ticket-{tipo['valor']}-{user.name}"[:95]

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            topic=tickets.construir_topic(
                user.id,
                tipo["valor"],
            ),
            reason=f"Ticket ({tipo['label']}) aberto por {user}",
        )

        embed = criar_embed(
            f"✦・ NÊMESIS — {tipo['label'].upper()} ・✦",
            (
                f"Olá, {user.mention}. Seu atendimento foi iniciado com sucesso.\n\n"
                "╭──────────── ◈ ATENDIMENTO ◈ ────────────╮\n"
                "➜ Explique sua solicitação com detalhes.\n"
                "➜ Envie provas, imagens ou contexto quando necessário.\n"
                "➜ Aguarde a equipe responsável responder.\n"
                "➜ Use **Fechar Ticket** quando o atendimento terminar.\n"
                "╰─────────────────────────────────────────╯"
            ),
            rodape="NÊMESIS • Central de atendimento privada",
            timestamp=True,
        )
        embed.add_field(name="Categoria", value=tipo["label"][:1024], inline=True)
        embed.add_field(name="Solicitante", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Status", value="🟢 Aguardando atendimento", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)

        try:
            mensagem = await canal.send(
                embed=embed,
                view=FecharTicketView(),
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )

            # Salva o registro depois de publicar a mensagem inicial.
            ticket_salvo = await tickets.criar_ticket(
                guild_id=guild.id,
                usuario_id=user.id,
                tipo=tipo["valor"],
                canal_id=canal.id,
                mensagem_id=mensagem.id,
            )

            # Protege também contra duas instâncias do bot: se a persistência
            # retornar um ticket anterior, removemos o canal recém-criado.
            if str(ticket_salvo.get("canal_id")) != str(canal.id):
                canal_existente_id = int(ticket_salvo.get("canal_id") or 0)
                try:
                    await canal.delete(reason="Ticket duplicado detectado")
                except (discord.Forbidden, discord.HTTPException):
                    logging.getLogger(__name__).exception(
                        "Falha ao remover ticket duplicado %s.",
                        canal.id,
                    )
                canal_existente = guild.get_channel(canal_existente_id)
                if canal_existente is not None:
                    return canal_existente
                raise RuntimeError("Já havia um ticket aberto, mas seu canal não foi encontrado.")
        except Exception:
            # Sem registro persistido, não deixamos um canal privado órfão.
            try:
                await canal.delete(reason="Falha ao inicializar/persistir ticket NÊMESIS")
            except (discord.Forbidden, discord.HTTPException):
                logging.getLogger(__name__).exception(
                    "Falha ao remover canal órfão de ticket %s.",
                    canal.id,
                )
            raise

        ULTIMA_ATIVIDADE[canal.id] = time.time()

        if not tipo["usa_ia"] and cargo_suporte:
            await canal.send(
                f"🔔 {cargo_suporte.mention} — novo ticket de "
                f"**{tipo['label']}**."
            )

        return canal

    @commands.Cog.listener()
    async def on_interaction(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.type != discord.InteractionType.component:
            return

        if interaction.data.get("custom_id") != CUSTOM_ID_SELECT:
            return

        valor_escolhido = interaction.data["values"][0]

        tipos = await tickets.get_tipos(
            interaction.guild.id
        )

        tipo = next(
            (
                t
                for t in tipos
                if t["valor"] == valor_escolhido
            ),
            None,
        )

        if not tipo:
            await interaction.response.send_message(
                "Essa categoria não existe mais. Avise um admin.",
                ephemeral=True,
            )
            return

        # Responde antes de acessar o armazenamento/criar canal, para não
        # deixar a interação do Discord expirar enquanto aguarda a operação.
        await interaction.response.defer(ephemeral=True, thinking=True)

        async with ABERTURA_TICKET_LOCK:
            # A consulta fica dentro do lock: dois cliques simultâneos do
            # mesmo usuário não criam dois canais.
            ticket_aberto = await tickets.get_ticket_aberto_usuario(
                interaction.guild.id,
                interaction.user.id,
            )

            if ticket_aberto:
                try:
                    canal_existente_id = int(ticket_aberto.get("canal_id", 0) or 0)
                except (TypeError, ValueError):
                    canal_existente_id = 0
                canal_existente = interaction.guild.get_channel(canal_existente_id)

                if canal_existente:
                    await interaction.followup.send(
                        f"Você já possui um ticket aberto: {canal_existente.mention}",
                        ephemeral=True,
                    )
                    return

                # Canal apagado manualmente: encerra o registro antigo.
                await tickets.fechar_ticket(
                    interaction.guild.id,
                    ticket_aberto["id"],
                    fechado_por_id=interaction.user.id,
                    motivo="Canal do ticket não foi encontrado.",
                )

            try:
                canal = await self._criar_canal_ticket(
                    interaction.guild,
                    interaction.user,
                    tipo,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Falha ao criar ticket para usuário %s (tipo=%s).",
                    interaction.user.id,
                    tipo.get("valor"),
                )
                await interaction.followup.send(
                    "Não consegui criar o ticket. Verifique as permissões do bot e tente novamente.",
                    ephemeral=True,
                )
                return

        await interaction.followup.send(
            f"✅ Ticket criado: {canal.mention}",
            ephemeral=True,
        )

    async def _chamar_suporte(
        self,
        message: discord.Message,
        motivo: str,
    ):
        CANAIS_ESCALADOS.add(
            message.channel.id
        )

        config = await get_config(
            message.guild.id
        )

        cargo_id = config["support_role_id"]

        mencao = (
            f"<@&{cargo_id}>"
            if cargo_id
            else "Equipe de suporte"
        )

        await message.channel.send(
            f"🔔 {mencao} — {motivo}"
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):
        if message.author.bot or not message.guild:
            return

        # O listener também recebe eventos de canais de voz; somente canais
        # de texto e tópicos possuem metadados de ticket e atributo topic.
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        info_topic = tickets.parse_topic(
            message.channel.topic if isinstance(message.channel, discord.TextChannel) else None
        )

        if not info_topic:
            return

        ULTIMA_ATIVIDADE[
            message.channel.id
        ] = time.time()

        # Registra quem realizou o atendimento.
        config = await get_config(
            message.guild.id
        )

        cargo_suporte_id = config.get(
            "support_role_id"
        )

        try:
            cargo_suporte_id = int(cargo_suporte_id) if cargo_suporte_id else None
        except (TypeError, ValueError):
            cargo_suporte_id = None

        cargo_suporte = (
            message.guild.get_role(cargo_suporte_id)
            if cargo_suporte_id
            else None
        )
        eh_suporte = bool(
            isinstance(message.author, discord.Member)
            and (
                message.author.guild_permissions.administrator
                or (
                    cargo_suporte is not None
                    and any(
                        cargo.id != message.guild.default_role.id
                        and cargo.position >= cargo_suporte.position
                        for cargo in message.author.roles
                    )
                )
            )
        )

        ticket_atual = await tickets.get_ticket_por_canal(
            message.guild.id,
            message.channel.id,
        )

        if ticket_atual and eh_suporte and not ticket_atual.get("atendido_por_id"):
            await tickets.registrar_atendimento(
                message.guild.id,
                ticket_atual["id"],
                message.author.id,
            )

        texto = _normalizar(
            message.content
        )

        pediu_fechamento = any(
            frase in texto
            for frase in FRASES_FECHAR
        )
        eh_dono_ticket = (
            ticket_atual is not None
            and ticket_atual.get("status") == "aberto"
            and str(message.author.id) == str(ticket_atual.get("usuario_id"))
        )
        eh_admin_ticket = (
            isinstance(message.author, discord.Member)
            and (
                message.author.guild_permissions.administrator
                or message.author.guild_permissions.manage_channels
            )
        )
        responsavel_id = ticket_atual.get("atendido_por_id") if ticket_atual else None
        permitido_fechar = (
            eh_dono_ticket
            or eh_admin_ticket
            or (
                eh_suporte
                and (
                    not responsavel_id
                    or str(message.author.id) == str(responsavel_id)
                )
            )
        )

        if (
            pediu_fechamento
            and ticket_atual is not None
            and ticket_atual.get("status") == "aberto"
            and permitido_fechar
        ):
            await fechar_canal_ticket(
                message.channel,
                f"Fechamento solicitado por usuário autorizado ({message.author.id}).",
                delay=5,
                fechado_por_id=message.author.id,
            )
            return

        # A partir daqui, só reage a mensagens do dono
        # do ticket (o cliente), não a mensagens da equipe.
        if str(message.author.id) != info_topic["owner_id"]:
            return

        if message.channel.id in CANAIS_ESCALADOS:
            return

        tipos = await tickets.get_tipos(
            message.guild.id
        )

        tipo = next(
            (
                t
                for t in tipos
                if t["valor"] == info_topic["tipo"]
            ),
            None,
        )

        if not tipo or not tipo["usa_ia"]:
            return

        if (
            "falar com atendente" in texto
            or "quero um humano" in texto
            or "atendente" in texto
        ):
            await self._chamar_suporte(
                message,
                "Cliente solicitou atendimento humano.",
            )
            return

        resultado = _resolver_problema(
            message.content,
            self.base_conhecimento,
        )

        if not resultado:
            await self._chamar_suporte(
                message,
                "Não consegui identificar automaticamente o seu problema.",
            )
            return

        embed = criar_embed(
            "N̷ÊMESIS ━ RESPOSTA AUTOMÁTICA",
            resultado["resposta"],
            rodape="NÊMESIS • Se precisar, solicite atendimento humano",
        )

        await message.reply(
            embed=embed
        )

        if resultado.get("escalar_sempre"):
            await self._chamar_suporte(
                message,
                "Este assunto precisa da revisão de um atendente humano.",
            )

    @tasks.loop(seconds=300)
    async def verificar_painel_permanente(self):
        for guild in self.bot.guilds:
            try:
                config = await get_config(guild.id)

                # Migra o menu padrão sem exigir comandos administrativos.
                if not config.get("ticket_modelo_v3"):
                    await tickets.set_tipos(
                        guild.id,
                        list(tickets.TIPOS_PADRAO),
                    )
                    await set_config(
                        guild.id,
                        ticket_modelo_v2=True,
                        ticket_modelo_v3=True,
                    )
                    config = await get_config(guild.id)

                canal_id = TICKET_PAINEL_CANAL_ID
                mensagem_id = config.get("ticket_painel_mensagem_id")
                canal = guild.get_channel(int(canal_id))
                if not isinstance(canal, discord.TextChannel):
                    continue

                embed = await _montar_embed_painel(guild.id)
                view = await _montar_select(guild.id)

                if mensagem_id:
                    try:
                        mensagem_existente = await canal.fetch_message(int(mensagem_id))
                        # Atualiza apenas quando o conteúdo visual mudou; evita
                        # editar o painel a cada ciclo e consumir limites do Discord.
                        embed_atual = (
                            mensagem_existente.embeds[0].to_dict()
                            if mensagem_existente.embeds
                            else None
                        )
                        if embed_atual != embed.to_dict():
                            await mensagem_existente.edit(embed=embed, view=view)
                        continue
                    except discord.NotFound:
                        pass
                    except (discord.Forbidden, discord.HTTPException):
                        continue

                mensagem = await canal.send(
                    embed=embed,
                    view=view,
                )
                try:
                    await mensagem.pin(
                        reason="Restaurando o painel permanente de tickets NÊMESIS"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

                await set_config(
                    guild.id,
                    ticket_painel_canal_id=canal.id,
                    ticket_painel_mensagem_id=mensagem.id,
                )
            except Exception as erro:
                print(
                    f"[Tickets] Falha ao restaurar painel no servidor {guild.id}: {erro}"
                )

    @verificar_painel_permanente.before_loop
    async def antes_de_verificar_painel_permanente(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time()

        for guild in self.bot.guilds:
            try:
                abertos = await tickets.listar_tickets(
                    guild.id,
                    status="aberto",
                )

                for ticket in abertos:
                    try:
                        canal_id = int(ticket.get("canal_id") or 0)
                    except (TypeError, ValueError):
                        canal_id = 0

                    if not canal_id:
                        continue

                    canal = guild.get_channel(canal_id)
                    if canal is None:
                        try:
                            canal = await guild.fetch_channel(canal_id)
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            await tickets.fechar_ticket(
                                guild.id,
                                ticket["id"],
                                motivo="Canal do ticket removido ou inacessível.",
                            )
                            continue

                    if not isinstance(canal, discord.TextChannel):
                        continue

                    ultima = ULTIMA_ATIVIDADE.get(canal.id)
                    if ultima is None:
                        # Após reiniciar, inicia a contagem no primeiro ciclo,
                        # evitando fechar tickets antigos sem verificar atividade.
                        ULTIMA_ATIVIDADE[canal.id] = agora
                        continue

                    if agora - ultima >= TEMPO_INATIVIDADE_SEGUNDOS:
                        await fechar_canal_ticket(
                            canal,
                            "Fechado automaticamente por 10 minutos de inatividade.",
                            delay=5,
                        )

            except Exception as erro:
                print(
                    "[Tickets] Falha ao verificar inatividade "
                    f"no servidor {guild.id}: {erro}"
                )

    @verificar_inatividade.before_loop
    async def antes_de_verificar_inatividade(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
