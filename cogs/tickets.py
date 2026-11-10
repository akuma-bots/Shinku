import time
import io
import asyncio
import logging
import re
import unicodedata
from urllib.parse import urlparse
import discord
from discord.ext import commands, tasks
from utils.apresentacao import criar_embed
from utils.storage import carregar_config
from utils.guild_config import get_config, set_config, membro_tem_lideranca
from utils import tickets
from utils.registro_global import obter_topico, registrar as registrar_global


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
TICKET_PAINEL_CANAL_ID = 1563995881655509057  # ticket-available no servidor atual

TITULO_PADRAO = "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE ATENDIMENTO ・✦"
COR_TICKET = 0x9F1239
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
            adquirido = await tickets.iniciar_fechamento_ticket(
                canal.guild.id,
                ticket["id"],
                fechado_por_id=fechado_por_id,
                motivo=motivo,
            )
            if not adquirido:
                return
            ticket = await tickets.get_ticket(canal.guild.id, ticket["id"]) or ticket
            historico_ok = await _publicar_historico_ticket(
                canal, ticket, motivo, fechado_por_id
            )
            if not historico_ok:
                raise RuntimeError(
                    f"Histórico do ticket {ticket['id']} não foi preservado; "
                    "canal mantido para nova tentativa."
                )


        await canal.send(f"🔒 Fechando este ticket em {delay}s. Motivo: {motivo}")
        await asyncio.sleep(max(0, delay))
        await canal.delete(reason=motivo)
        if ticket:
            await tickets.finalizar_fechamento_ticket(
                canal.guild.id,
                ticket["id"],
            )

        if ticket and not ticket.get("avaliacao_solicitada"):
            await tickets.atualizar_ticket(
                canal.guild.id,
                ticket["id"],
                avaliacao_solicitada=True,
            )
            dono = canal.guild.get_member(int(ticket.get("usuario_id") or 0))
            if dono:
                try:
                    embed = criar_embed(
                        "✦・ NÊMESIS — AVALIAÇÃO DE ATENDIMENTO ・✦",
                        f"Seu atendimento #{ticket.get('id', '—')} foi encerrado.\n\nSua avaliação é necessária para concluir o atendimento. Escolha uma nota de 1 a 5 abaixo.",
                        rodape="NÊMESIS • Central de atendimento",
                    )
                    await dono.send(view=AvaliacaoTicketLayoutView(
                        canal.guild.id, str(ticket["id"]), int(ticket.get("usuario_id") or 0),
                        int(ticket.get("atendido_por_id") or 0),
                    ))
                except discord.Forbidden:
                    logging.info("Não foi possível enviar a avaliação por DM; usuário %s.", ticket.get("usuario_id"))
                except discord.HTTPException:
                    logging.exception("Falha ao enviar prompt de avaliação do ticket.")


    except discord.NotFound:
        # Mesmo que o canal já tenha sido apagado, tenta manter
        # o registro persistente como fechado.
        try:
            ticket = await tickets.get_ticket_por_canal(canal.guild.id, canal.id)

            if ticket:
                if ticket.get("status") == "fechando":
                    await tickets.finalizar_fechamento_ticket(
                        canal.guild.id,
                        ticket["id"],
                    )
                else:
                    await tickets.fechar_ticket(
                        canal.guild.id,
                        ticket["id"],
                        fechado_por_id=fechado_por_id,
                        motivo=motivo,
                    )
        except Exception:
            logging.exception(
                "Falha ao reconciliar o registro persistente do ticket após canal já removido "
                "(guild=%s, canal=%s, ticket=%s).",
                canal.guild.id,
                canal.id,
                "indisponível",
            )

    except Exception:
        raise

    finally:
        CANAIS_FECHANDO.discard(canal.id)


def _emoji_personalizado(guild: discord.Guild | None, tipo: dict):
    """Resolve os emblemas TicketEmoji1..8 cadastrados no servidor."""
    if guild is None:
        return None

    nomes_por_categoria = {
        "recrutamento": ("emoji_8", "TicketEmoji8"),
        "hierarquia_divisoes": ("emoji_7", "TicketEmoji6"),
        "conflitos_denuncias": ("emoji_6", "TicketEmoji4"),
        "guerras_desafios": ("emoji_5", "TicketEmoji2"),
        "suporte_comunidade": ("emoji_4", "TicketEmoji7"),
        "aliancas": ("emoji_3", "TicketEmoji5"),
        "eventos_atividades": ("emoji_2", "TicketEmoji3"),
        "sugestoes_projetos": ("emoji_1", "TicketEmoji1"),
    }
    nomes = nomes_por_categoria.get(tipo.get("valor"), ())
    for nome in nomes:
        emoji = discord.utils.get(guild.emojis, name=nome)
        if emoji is not None:
            return emoji
    return None


async def _montar_select(guild_id: int, guild: discord.Guild | None = None) -> discord.ui.LayoutView:
    """Painel de atendimento em Components V2, com seletor dentro do cartão."""
    config = await get_config(guild_id)
    tipos = await tickets.get_tipos(guild_id) or list(tickets.TIPOS_PADRAO)
    options = []
    for tipo in tipos[:25]:
        emoji = _emoji_personalizado(guild, tipo) or tipo.get("emoji") or "◈"
        options.append(discord.SelectOption(
            label=str(tipo.get("label") or "Atendimento")[:100],
            value=str(tipo.get("valor") or "outro")[:100],
            description=str(tipo.get("descricao") or "Solicitação de atendimento.")[:100],
            emoji=emoji,
        ))
    seletor = discord.ui.Select(
        placeholder="Escolha o assunto do atendimento",
        options=options,
        custom_id=CUSTOM_ID_SELECT,
    )

    avatar = guild.me.display_avatar.url if guild and guild.me else None
    itens = []
    banner = config.get("ticket_painel_banner_url")
    if banner:
        itens.append(discord.ui.MediaGallery(
            discord.MediaGalleryItem(url=banner, description="Nêmesis • Atendimento")
        ))

    titulo = str(config.get("ticket_painel_titulo") or TITULO_PADRAO)
    descricao = str(config.get("ticket_painel_descricao") or DESCRICAO_PADRAO)
    texto = (
        f"## 🎟️ {titulo}\n"
        "**NÊMESIS  /  CENTRAL DE ATENDIMENTO**\n"
        f"{descricao}\n\n"
        "Escolha uma categoria para abrir seu canal privado."
    )
    if avatar:
        itens.append(discord.ui.Section(
            discord.ui.TextDisplay(texto),
            accessory=discord.ui.Thumbnail(avatar, description="Ícone do bot Nêmesis"),
        ))
    else:
        itens.append(discord.ui.TextDisplay(texto))

    itens.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("### ◈  ASSUNTOS DO ATENDIMENTO"),
    ])
    for tipo in tipos[:8]:
        emoji = str(_emoji_personalizado(guild, tipo) or tipo.get("emoji") or "◈")
        nome = str(tipo.get("label") or "Atendimento")[:80]
        detalhe = str(tipo.get("descricao") or "Solicitação direcionada à equipe.")[:180]
        itens.append(discord.ui.TextDisplay(f"{emoji} **{nome}**\n{detalhe}"))

    itens.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(
            "**Privado • Seguro • Direcionado**\n"
            "O canal será visível somente para você e a equipe autorizada. "
            "Nunca compartilhe senhas, tokens ou códigos de autenticação."
        ),
        discord.ui.ActionRow(seletor),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam"),
    ])
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*itens, accent_colour=COR_TICKET))
    return view


CANAL_AVALIACOES_TICKET_ID = 1563995881806758056


async def _publicar_historico_ticket(canal, ticket, motivo, fechado_por_id):
    if ticket.get("historico_publicado"):
        return True
    try:
        destino = await obter_topico(canal.guild, "atendimento")
        if destino.archived:
            await destino.edit(archived=False, reason="Preservar transcrição de atendimento")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
        logging.exception("Tópico permanente de Atendimento indisponível.")
        return False
    usuario_id = int(ticket.get("usuario_id") or 0)
    atendente_id = int(ticket.get("atendido_por_id") or 0)
    registros = await tickets.listar_tickets(canal.guild.id)
    atendidos = [t for t in registros if isinstance(t, dict) and str(t.get("atendido_por_id") or "") == str(atendente_id) and t.get("status") in {"fechando", "fechado"}] if atendente_id else []
    notas = [int(t["avaliacao"]) for t in atendidos if str(t.get("avaliacao", "")).isdigit() and 1 <= int(t["avaliacao"]) <= 5]
    media = sum(notas) / len(notas) if notas else None
    try:
        mensagens = [m async for m in canal.history(limit=None, oldest_first=True)]
    except (discord.Forbidden, discord.HTTPException):
        logging.exception("Não foi possível ler o histórico do ticket %s", ticket.get("id"))
        return False
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
        descricao_fechamento = f"Cliente: <@{usuario_id}> (`{usuario_id}`)\n"
        descricao_fechamento += (
            f"Responsável: <@{atendente_id}> (`{atendente_id}`)"
            if atendente_id else "Responsável: Não atribuído"
        )
        descricao_fechamento += f"\nMotivo: {motivo}\nFechado por: {fechado_por_id or 'sistema'}"
        await registrar_global(
            canal.guild,
            "atendimento",
            f"Ticket #{ticket.get('id', '—')} encerrado",
            descricao_fechamento,
            cor=0xB3132B,
        )
        await tickets.atualizar_ticket(
            canal.guild.id,
            ticket["id"],
            historico_publicado=True,
            historico_publicado_em=time.time(),
        )
        return True
    except (discord.Forbidden, discord.HTTPException):
        logging.exception("Falha ao publicar a transcrição do ticket %s", ticket.get("id"))
        return False


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
        if interaction.user.id != self.owner_id:
            await interaction.followup.send(
                "Somente quem abriu o ticket pode enviar esta avaliação.",
                ephemeral=True,
            )
            return
        if not ticket or ticket.get("status") != "fechado":
            await interaction.followup.send("Este ticket não foi encontrado ou ainda não foi encerrado.", ephemeral=True)
            return
        if str(ticket.get("usuario_id")) != str(self.owner_id) or ticket.get("avaliacao") is not None:
            await interaction.followup.send("Esta avaliação já foi enviada ou não pertence a este atendimento.", ephemeral=True)
            return
        comentario = str(self.comentario.value or "").strip()
        atualizado = await tickets.registrar_avaliacao(
            self.guild_id,
            self.ticket_id,
            self.nota,
            comentario,
            time.time(),
        )
        if not atualizado:
            await interaction.followup.send(
                "Esta avaliação já foi registrada ou o atendimento não está encerrado.",
                ephemeral=True,
            )
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
            embed = criar_embed(
                "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — AVALIAÇÃO DE ATENDIMENTO ・✦",
                f"**Ticket #{self.ticket_id}** · avaliação confirmada\n\n"
                "O feedback abaixo foi enviado pelo responsável pelo ticket e será usado "
                "para acompanhar a qualidade da Central de Atendimento.",
                rodape="NÊMESIS • Qualidade e experiência do membro",
            )
            embed.color = 0xB3132B
            embed.add_field(
                name="◈ NOTA DO ATENDIMENTO",
                value=f"**{self.nota}/5 — {rotulo}**\n{'⭐' * self.nota}",
                inline=True,
            )
            embed.add_field(
                name="◈ CLIENTE",
                value=f"<@{self.owner_id}>\nID: `{self.owner_id}`",
                inline=True,
            )
            embed.add_field(
                name="◈ RESPONSÁVEL",
                value=f"<@{self.atendente_id}>\nID: `{self.atendente_id}`" if self.atendente_id else "Não identificado",
                inline=True,
            )
            embed.add_field(
                name="◈ COMENTÁRIO",
                value=(comentario[:1024] if comentario else "O cliente não deixou comentário."),
                inline=False,
            )
            embed.add_field(name="ATENDIMENTOS ENCERRADOS", value=str(total), inline=True)
            embed.add_field(name="MÉDIA DO RESPONSÁVEL", value=media_texto, inline=True)
            embed.add_field(
                name="REGISTRADO EM",
                value=discord.utils.format_dt(discord.utils.utcnow(), style="F"),
                inline=False,
            )
            try:
                await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                descricao_avaliacao = f"Cliente: <@{self.owner_id}> (`{self.owner_id}`)\n"
                descricao_avaliacao += (
                    f"Responsável: <@{self.atendente_id}> (`{self.atendente_id}`)"
                    if self.atendente_id else "Responsável: Não identificado"
                )
                descricao_avaliacao += f"\nNota: **{self.nota}/5 — {rotulo}**\nComentário: {comentario or 'Não informado'}"
                await registrar_global(
                    guild,
                    "atendimento",
                    f"Avaliação do ticket #{self.ticket_id}",
                    descricao_avaliacao,
                    cor=0xB3132B,
                )
            except (discord.Forbidden, discord.HTTPException):
                logging.exception(
                    "Avaliação do ticket %s salva, mas não publicada no canal %s.",
                    self.ticket_id,
                    CANAL_AVALIACOES_TICKET_ID,
                )
        await interaction.followup.send(f"Obrigado pelo feedback! Sua avaliação foi registrada: {self.nota}/5 — {rotulo}.", ephemeral=True)


class AvaliacaoTicketButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ticket:avaliar:(?P<guild_id>\d{1,20}):(?P<ticket_id>[a-fA-F0-9]{8}):(?P<nota>[1-5])",
):
    def __init__(self, guild_id: int, ticket_id: str, nota: int):
        self.guild_id = int(guild_id)
        self.ticket_id = str(ticket_id)
        self.nota = int(nota)
        super().__init__(
            discord.ui.Button(
                label=f"{self.nota}/5",
                emoji="⭐",
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket:avaliar:{self.guild_id}:{self.ticket_id}:{self.nota}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(
            int(match["guild_id"]),
            match["ticket_id"],
            int(match["nota"]),
        )

    async def callback(self, interaction: discord.Interaction):
        ticket = await tickets.get_ticket(self.guild_id, self.ticket_id)
        if not ticket or str(interaction.user.id) != str(ticket.get("usuario_id")):
            await interaction.response.send_message(
                "Somente quem abriu o ticket pode avaliá-lo.",
                ephemeral=True,
            )
            return
        if ticket.get("status") != "fechado":
            await interaction.response.send_message(
                "Este ticket ainda não foi encerrado.",
                ephemeral=True,
            )
            return
        if ticket.get("avaliacao") is not None:
            await interaction.response.send_message(
                "Você já avaliou este atendimento.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            FeedbackTicketModal(
                self.guild_id,
                self.ticket_id,
                int(ticket.get("usuario_id") or 0),
                int(ticket.get("atendido_por_id") or 0),
                self.nota,
            )
        )


class AvaliacaoTicketView(discord.ui.View):
    def __init__(self, guild_id: int, ticket_id: str, owner_id: int, atendente_id: int):
        super().__init__(timeout=None)
        for nota in range(1, 6):
            self.add_item(AvaliacaoTicketButton(guild_id, ticket_id, nota))


class AvaliacaoTicketLayoutView(discord.ui.LayoutView):
    """Apresenta as notas dentro de um cartão Components V2."""

    def __init__(self, guild_id: int, ticket_id: str, owner_id: int, atendente_id: int):
        super().__init__(timeout=None)
        botoes = [
            discord.ui.Button(
                label=f"{nota}/5",
                emoji="⭐",
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket:avaliar:{guild_id}:{ticket_id}:{nota}",
            )
            for nota in range(1, 6)
        ]
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## ✦ NÊMESIS — AVALIAÇÃO DE ATENDIMENTO\n"
                f"**Ticket #{ticket_id}**\n"
                "Como foi sua experiência? Selecione uma nota de 1 a 5."
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(*botoes[:5]),
            discord.ui.TextDisplay("-# Nêmesis Systeam • Central de Atendimento"),
            accent_colour=COR_TICKET,
        ))


class FecharTicketLayoutView(discord.ui.LayoutView):
    """Mantém apresentação e controles operacionais do ticket no mesmo cartão."""

    def __init__(self, origem: discord.ui.View | None = None, embed: discord.Embed | None = None):
        super().__init__(timeout=None)
        origem = origem or FecharTicketView()
        if embed is not None:
            partes = [f"## {embed.title or 'NÊMESIS • CENTRAL DE ATENDIMENTO'}"]
            if embed.description:
                partes.append(embed.description)
            for campo in embed.fields:
                partes.append(f"**{campo.name}**\n{campo.value}")
            if embed.footer and embed.footer.text:
                partes.append(f"-# {embed.footer.text}")
            origem._card_content = "\n\n".join(partes)[:3900]
        texto_cartao = getattr(
            origem,
            "_card_content",
            "## 🎟️ NÊMESIS — CENTRAL DE ATENDIMENTO\n"
            "Utilize os controles abaixo para assumir, encaminhar ou encerrar este atendimento.",
        )
        botoes_por_linha = {};
        for item in origem.children:
            if not isinstance(item, discord.ui.Button):
                continue
            botao = discord.ui.Button(
                label=item.label,
                style=item.style,
                disabled=item.disabled,
                custom_id=item.custom_id,
                url=item.url,
                emoji=item.emoji,
            )
            botao.callback = item.callback
            botoes_por_linha.setdefault(item.row or 0, []).append(botao)
        componentes = [
            discord.ui.TextDisplay(texto_cartao),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ]
        for _, botoes in sorted(botoes_por_linha.items()):
            for inicio in range(0, len(botoes), 5):
                componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
        componentes.extend([
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam • Atendimento privado"),
        ])
        self.add_item(discord.ui.Container(*componentes, accent_colour=COR_TICKET))


class AdicionarParticipanteModal(discord.ui.Modal, title="Adicionar participante ao ticket"):
    usuario = discord.ui.TextInput(label="ID ou menção do membro", placeholder="ID do Discord ou @membro", required=True, max_length=40)

    async def on_submit(self, interaction: discord.Interaction):
        canal, guild = interaction.channel, interaction.guild
        if not guild or not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message("Use esta ação dentro de um ticket.", ephemeral=True)
            return
        registro = await tickets.get_ticket_por_canal(guild.id, canal.id)
        if not registro or registro.get("status") != "aberto":
            await interaction.response.send_message("Este ticket não está ativo.", ephemeral=True)
            return
        config = await get_config(guild.id)
        role_id = config.get("support_role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        staff = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.manage_channels or
            (role and any(r != guild.default_role and r.position >= role.position for r in interaction.user.roles))
        )
        if str(interaction.user.id) != str(registro.get("usuario_id")) and not staff:
            await interaction.response.send_message("Somente o solicitante ou a equipe pode adicionar participantes.", ephemeral=True)
            return
        alvo_id = re.sub(r"\D", "", str(self.usuario.value))
        try:
            alvo = guild.get_member(int(alvo_id)) or await guild.fetch_member(int(alvo_id))
        except (ValueError, discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("Não encontrei esse membro neste servidor.", ephemeral=True)
            return
        if alvo.bot or alvo.id == int(registro.get("usuario_id") or 0):
            await interaction.response.send_message("Esse membro não pode ser adicionado.", ephemeral=True)
            return
        try:
            await canal.set_permissions(alvo, view_channel=True, send_messages=True, read_message_history=True, reason=f"Participante adicionado por {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("Não consegui conceder acesso. Verifique as permissões do bot.", ephemeral=True)
            return
        embed = criar_embed("♧  PARTICIPANTE ADICIONADO", f"{alvo.mention} recebeu acesso ao atendimento.", cor=COR_TICKET, rodape="NÊMESIS  •  CONTROLE DE ACESSO")
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))


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
            await interaction.message.edit(view=FecharTicketLayoutView(self))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.warning("Não foi possível atualizar os botões do ticket %s após atribuir atendimento.", canal.id)
        await interaction.followup.send(
            f"✅ Você agora é responsável por {canal.mention}. "
            "A equipe comum não pode intervir; a administração continua com acesso.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Adicionar participante",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:adicionar_participante",
        row=1,
    )
    async def adicionar_participante(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel
        if not isinstance(canal, discord.TextChannel) or not tickets.parse_topic(canal.topic):
            await interaction.response.send_message("Use este recurso dentro de um ticket.", ephemeral=True)
            return
        await interaction.response.send_modal(AdicionarParticipanteModal())

    @discord.ui.button(
        label="Solicitar equipe",
        emoji="🔔",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:solicitar_equipe",
        row=1,
    )
    async def solicitar_equipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal, guild = interaction.channel, interaction.guild
        if not guild or not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message("Use este recurso dentro de um ticket.", ephemeral=True)
            return
        registro = await tickets.get_ticket_por_canal(guild.id, canal.id)
        if not registro or registro.get("status") != "aberto":
            await interaction.response.send_message("Este ticket não está aberto.", ephemeral=True)
            return
        config = await get_config(guild.id)
        role_id = config.get("support_role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        staff = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.manage_channels or
            (role and any(r != guild.default_role and r.position >= role.position for r in interaction.user.roles))
        )
        if str(interaction.user.id) != str(registro.get("usuario_id")) and not staff:
            await interaction.response.send_message("Somente o solicitante ou a equipe pode solicitar atendimento.", ephemeral=True)
            return
        if canal.id in CANAIS_ESCALADOS:
            await interaction.response.send_message("A equipe já foi notificada neste atendimento.", ephemeral=True)
            return
        CANAIS_ESCALADOS.add(canal.id)
        embed = criar_embed("🔔  EQUIPE NOTIFICADA", "Sua solicitação foi encaminhada à equipe. Aguarde o retorno neste canal.", cor=COR_TICKET, rodape="NÊMESIS  •  ESCALONAMENTO")
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await canal.send(
            f"{role.mention if role else 'Equipe de suporte'} — atendimento solicitado em {canal.mention}.",
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
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


async def sincronizar_painel_ticket(guild: discord.Guild) -> discord.Message:
    config = await get_config(guild.id)
    canal_id = int(config.get("ticket_painel_canal_id") or TICKET_PAINEL_CANAL_ID)
    canal = guild.get_channel(canal_id)
    if canal is None:
        canal = await guild.fetch_channel(canal_id)
    if not isinstance(canal, discord.TextChannel):
        raise RuntimeError("O canal configurado para o painel de tickets não é um canal de texto.")

    view = await _montar_select(guild.id, guild)
    mensagem = None
    mensagem_id = config.get("ticket_painel_mensagem_id")
    if mensagem_id:
        try:
            mensagem = await canal.fetch_message(int(mensagem_id))
        except discord.NotFound:
            mensagem = None

    if mensagem is not None:
        await mensagem.edit(content=None, embeds=[], attachments=[], view=view)
    else:
        mensagem = await canal.send(view=view)
        try:
            await mensagem.pin(reason="Central permanente de atendimento NÊMESIS")
        except (discord.Forbidden, discord.HTTPException):
            log.warning("Não foi possível fixar o painel de tickets no canal %s.", canal.id)

    await set_config(
        guild.id,
        ticket_painel_canal_id=canal.id,
        ticket_painel_mensagem_id=mensagem.id,
    )
    return mensagem


class SeletorCategoriaTickets(discord.ui.ChannelSelect):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Selecionar categoria onde os tickets serão criados",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.category],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        categoria = self.values[0]
        await set_config(
            self.central.guild.id,
            ticket_category_id=categoria.id,
        )
        await interaction.response.edit_message(
            embed=await self.central.criar_embed(),
            view=self.central,
        )


class SeletorEquipeTickets(discord.ui.RoleSelect):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Selecionar cargo responsável pelo atendimento",
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        cargo = self.values[0]
        if cargo.is_default():
            await interaction.response.send_message(
                "O cargo @everyone não pode ser usado como equipe de atendimento.",
                ephemeral=True,
            )
            return
        await set_config(
            self.central.guild.id,
            support_role_id=cargo.id,
        )
        await interaction.response.edit_message(
            embed=await self.central.criar_embed(),
            view=self.central,
        )


class EditarCategoriaTicketModal(discord.ui.Modal, title="Personalizar categoria de atendimento"):
    nome = discord.ui.TextInput(label="Nome exibido", required=True, max_length=100)
    emoji = discord.ui.TextInput(label="Emoji", required=True, max_length=64)
    descricao = discord.ui.TextInput(
        label="Descrição",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=100,
    )

    def __init__(self, central, tipo: dict):
        super().__init__(timeout=180)
        self.central = central
        self.valor = str(tipo.get("valor") or "")
        self.nome.default = str(tipo.get("label") or "")[:100]
        self.emoji.default = str(tipo.get("emoji") or "◈")[:64]
        self.descricao.default = str(tipo.get("descricao") or "")[:100]

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        tipo = await tickets.atualizar_tipo_visual(
            self.central.guild.id,
            self.valor,
            self.emoji.value,
            self.descricao.value,
            self.nome.value,
        )
        if not tipo:
            await interaction.response.send_message(
                "A categoria não existe mais. Atualize a central e tente novamente.",
                ephemeral=True,
            )
            return
        try:
            mensagem = await sincronizar_painel_ticket(self.central.guild)
            await interaction.response.send_message(
                f"Categoria **{tipo['label']}** atualizada. Painel sincronizado: {mensagem.jump_url}",
                ephemeral=True,
            )
        except Exception:
            log.exception("Falha ao sincronizar o painel após editar categoria de ticket.")
            await interaction.response.send_message(
                "A categoria foi salva, mas o painel não pôde ser sincronizado. Use Atualizar painel na central.",
                ephemeral=True,
            )


class PersonalizarPainelTicketModal(discord.ui.Modal, title="Personalizar painel de atendimento"):
    titulo = discord.ui.TextInput(label="Título do painel", required=False, max_length=240)
    descricao = discord.ui.TextInput(
        label="Descrição",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1500,
    )
    banner = discord.ui.TextInput(label="Banner HTTPS (opcional)", required=False, max_length=500)
    icone = discord.ui.TextInput(label="Ícone HTTPS (opcional)", required=False, max_length=500)

    def __init__(self, central, config: dict):
        super().__init__(timeout=180)
        self.central = central
        self.titulo.default = str(config.get("ticket_painel_titulo") or TITULO_PADRAO)[:240]
        self.descricao.default = str(config.get("ticket_painel_descricao") or DESCRICAO_PADRAO)[:1500]
        self.banner.default = str(config.get("ticket_painel_banner_url") or "")[:500]
        self.icone.default = str(config.get("ticket_painel_thumbnail_url") or "")[:500]

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        updates = {
            "ticket_painel_titulo": str(self.titulo.value).strip()[:240],
            "ticket_painel_descricao": str(self.descricao.value).strip()[:1500],
        }
        for chave, valor in (
            ("ticket_painel_banner_url", self.banner.value),
            ("ticket_painel_thumbnail_url", self.icone.value),
        ):
            valor = str(valor or "").strip()
            if valor:
                parsed = urlparse(valor)
                if parsed.scheme != "https" or not parsed.netloc:
                    await interaction.response.send_message(
                        "Banner e ícone precisam usar URLs HTTPS válidas.",
                        ephemeral=True,
                    )
                    return
            updates[chave] = valor
        await set_config(self.central.guild.id, **updates)
        try:
            mensagem = await sincronizar_painel_ticket(self.central.guild)
            await interaction.response.send_message(
                f"Painel personalizado e publicado: {mensagem.jump_url}",
                ephemeral=True,
            )
        except Exception:
            log.exception("Falha ao publicar painel de tickets personalizado.")
            await interaction.response.send_message(
                "As configurações foram salvas, mas não consegui atualizar o painel. Tente Atualizar painel na central.",
                ephemeral=True,
            )


class CentralTicketsView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.owner_id = int(owner_id)
        self.add_item(SeletorCategoriaTickets(self))
        self.add_item(SeletorEquipeTickets(self))
        self.seletor_tipos = None

    async def configurar(self):
        tipos = await tickets.get_tipos(self.guild.id)
        if tipos:
            options = [
                discord.SelectOption(
                    label=str(tipo.get("label") or "Atendimento")[:100],
                    value=str(tipo.get("valor") or "outro")[:100],
                    description=str(tipo.get("descricao") or "Categoria de atendimento.")[:100],
                    emoji=str(tipo.get("emoji") or "◈"),
                )
                for tipo in tipos[:25]
            ]
            self.seletor_tipos = discord.ui.Select(
                placeholder="Selecionar categoria para personalizar",
                min_values=1,
                max_values=1,
                options=options,
                row=2,
            )
            self.seletor_tipos.callback = self.editar_categoria
            self.add_item(self.seletor_tipos)
        return self

    async def autorizar(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild.id
            or interaction.user.id != self.owner_id
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "Esta central pertence à liderança que a abriu ou seu acesso expirou.",
                ephemeral=True,
            )
            return False
        return True

    async def editar_categoria(self, interaction: discord.Interaction):
        if not await self.autorizar(interaction):
            return
        valor = interaction.data.get("values", [None])[0]
        tipo = next(
            (item for item in await tickets.get_tipos(self.guild.id) if item.get("valor") == valor),
            None,
        )
        if not tipo:
            await interaction.response.send_message(
                "Categoria não encontrada. Atualize a central.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(EditarCategoriaTicketModal(self, tipo))

    async def criar_embed(self) -> discord.Embed:
        config = await get_config(self.guild.id)
        todos = await tickets.listar_tickets(self.guild.id)
        abertos = sum(item.get("status") == "aberto" for item in todos)
        fechando = sum(item.get("status") == "fechando" for item in todos)
        fechados = sum(item.get("status") == "fechado" for item in todos)
        categoria_id = config.get("ticket_category_id")
        suporte_id = config.get("support_role_id")
        painel_id = config.get("ticket_painel_canal_id") or TICKET_PAINEL_CANAL_ID
        embed = criar_embed(
            "Central de Gestão de Atendimento",
            "Configure o canal de criação, a equipe responsável, o visual do painel e as categorias de atendimento. "
            "As alterações são aplicadas sem comandos separados.",
        )
        embed.add_field(name="Tickets abertos", value=f"**{abertos}**", inline=True)
        embed.add_field(name="Fechamentos pendentes", value=f"**{fechando}**", inline=True)
        embed.add_field(name="Histórico", value=f"**{fechados}**", inline=True)
        embed.add_field(
            name="Categoria de criação",
            value=f"<#{categoria_id}>" if categoria_id else "Não configurada",
            inline=True,
        )
        embed.add_field(
            name="Equipe responsável",
            value=f"<@&{suporte_id}>" if suporte_id else "Não configurada",
            inline=True,
        )
        embed.add_field(name="Canal do painel", value=f"<#{painel_id}>", inline=True)
        embed.set_footer(text="Acesso exclusivo à liderança • NÊMESIS")
        return embed

    @discord.ui.button(label="Personalizar painel", style=discord.ButtonStyle.primary, emoji="🎨", row=3)
    async def personalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        await interaction.response.send_modal(
            PersonalizarPainelTicketModal(self, await get_config(self.guild.id))
        )

    @discord.ui.button(label="Atualizar painel", style=discord.ButtonStyle.success, emoji="🔄", row=3)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            mensagem = await sincronizar_painel_ticket(self.guild)
            await interaction.followup.send(
                f"Painel de atendimento sincronizado: {mensagem.jump_url}",
                ephemeral=True,
            )
        except Exception:
            log.exception("Falha ao sincronizar painel pela Central de Tickets.")
            await interaction.followup.send(
                "Não consegui atualizar o painel. Verifique as permissões e o canal configurado.",
                ephemeral=True,
            )

    @discord.ui.button(label="Fechar central", style=discord.ButtonStyle.secondary, emoji="❌", row=3)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Central de Gestão de Atendimento encerrada.",
            embed=None,
            view=self,
        )


class Tickets(commands.Cog):
    """
    Sistema de tickets por categoria.

    O painel público abre solicitações por categoria; a liderança gerencia
    configurações e categorias pela central administrativa integrada.

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

        bot.add_view(FecharTicketLayoutView())
        bot.add_dynamic_items(AvaliacaoTicketButton)

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

        descricao_tipo = str(tipo.get("descricao") or "Solicitação direcionada à equipe responsável.")
        embed = criar_embed(
            f"◈  ATENDIMENTO · {tipo['label'].upper()[:75]}",
            f"Olá, {user.mention}. Seu canal privado foi criado.\nA equipe responsável receberá sua solicitação neste espaço.",
            cor=0x9F1239,
            rodape="NÊMESIS  •  ATENDIMENTO PRIVADO  •  REGISTRO ATIVO",
            timestamp=True,
        )
        embed.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  CENTRAL DE OPERAÇÕES")
        embed.add_field(name="PROTOCOLO", value=f"**{tipo['label']}**\n{descricao_tipo[:300]}", inline=False)
        embed.add_field(name="SOLICITANTE", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="SITUAÇÃO", value="🟠  Aguardando responsável", inline=True)
        embed.add_field(name="PRÓXIMAS ETAPAS", value="01 — Descreva o que aconteceu e o resultado esperado.\n02 — Envie capturas, links ou IDs que ajudem na análise.\n03 — Aguarde a equipe; o responsável será identificado no atendimento.\n04 — Use Fechar Ticket somente quando o caso estiver resolvido.", inline=False)
        embed.add_field(name="PROTEÇÃO DE DADOS", value="Não compartilhe senhas, tokens, códigos de autenticação ou informações de acesso.", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        if config.get("ticket_painel_banner_url"):
            embed.set_image(url=config["ticket_painel_banner_url"])

        try:
            origem_view = FecharTicketView()
            mensagem = await canal.send(
                view=FecharTicketLayoutView(origem_view, embed),
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
                if canal_existente is None and canal_existente_id:
                    try:
                        canal_existente = await guild.fetch_channel(canal_existente_id)
                    except discord.NotFound:
                        canal_existente = None
                    except (discord.Forbidden, discord.HTTPException):
                        logging.getLogger(__name__).exception(
                            "Não foi possível recuperar o canal do ticket já existente %s.",
                            canal_existente_id,
                        )
                if isinstance(canal_existente, discord.TextChannel):
                    return canal_existente
                raise RuntimeError("Já havia um ticket aberto, mas seu canal não pôde ser recuperado.")
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
        await registrar_global(
            guild,
            "atendimento",
            f"Ticket #{ticket_salvo.get('id', '—')} aberto",
            f"Solicitante: {user.mention} (`{user.id}`)\n"
            f"Categoria: **{tipo.get('label', tipo.get('valor', 'Atendimento'))}**\n"
            f"Canal: {canal.mention} (`{canal.id}`)\nStatus: **Aguardando responsável**",
            cor=0x57F287,
        )

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
        if interaction.guild is None or interaction.user.bot:
            await interaction.response.send_message(
                "O painel de atendimento só funciona para membros dentro do servidor.",
                ephemeral=True,
            )
            return
        valores = interaction.data.get("values") or []
        if not valores:
            await interaction.response.send_message(
                "Nenhuma categoria foi selecionada. Atualize o painel e tente novamente.",
                ephemeral=True,
            )
            return

        valor_escolhido = str(valores[0])
        # Reconhece a interação antes de consultar o Redis.
        await _preparar_resposta_interacao(interaction)
        try:
            tipos = await tickets.get_tipos(interaction.guild.id)
        except Exception:
            log.exception("Falha ao carregar categorias do painel de tickets.")
            await interaction.followup.send(
                "Não consegui carregar as categorias agora. Tente novamente em instantes.",
                ephemeral=True,
            )
            return

        tipo = next(
            (
                t
                for t in tipos
                if t["valor"] == valor_escolhido
            ),
            None,
        )

        if not tipo:
            await interaction.followup.send(
                "Essa categoria não existe mais. Atualize o painel e tente novamente.",
                ephemeral=True,
            )
            return

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
                if canal_existente is None and canal_existente_id:
                    try:
                        canal_existente = await interaction.guild.fetch_channel(canal_existente_id)
                    except discord.NotFound:
                        canal_existente = None
                    except discord.Forbidden:
                        await interaction.followup.send(
                            "Encontrei um ticket aberto, mas não tenho permissão para verificar o canal. A equipe técnica precisa revisar as permissões.",
                            ephemeral=True,
                        )
                        return
                    except discord.HTTPException:
                        await interaction.followup.send(
                            "Não consegui consultar seu ticket existente agora. Tente novamente em instantes.",
                            ephemeral=True,
                        )
                        return

                if isinstance(canal_existente, discord.TextChannel):
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
            assumido = await tickets.registrar_atendimento(
                message.guild.id,
                ticket_atual["id"],
                message.author.id,
            )
            if assumido:
                await registrar_global(
                    message.guild,
                    "atendimento",
                    f"Ticket #{ticket_atual.get('id', '—')} atribuído",
                    f"Responsável: {message.author.mention} (`{message.author.id}`)\n"
                    f"Solicitante: <@{ticket_atual.get('usuario_id')}>\n"
                    f"Canal: {message.channel.mention}",
                    cor=0xFEE75C,
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

    async def abrir_central(self, interaction: discord.Interaction, owner_id: int):
        if (
            interaction.guild is None
            or interaction.user.id != int(owner_id)
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "A Central de Gestão de Atendimento é restrita à liderança autorizada.",
                ephemeral=True,
            )
            return
        view = await CentralTicketsView(self, interaction.guild, owner_id).configurar()
        await interaction.response.send_message(
            embed=await view.criar_embed(),
            view=view,
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Aplica a versão atual do painel assim que o bot fica pronto."""
        for guild in self.bot.guilds:
            try:
                mensagem = await sincronizar_painel_ticket(guild)
                log.info(
                    "Central de atendimento sincronizada no Discord (guild=%s, canal=%s, mensagem=%s, components_v2=True).",
                    guild.id,
                    mensagem.channel.id,
                    mensagem.id,
                )
            except Exception:
                log.exception(
                    "Falha ao sincronizar a Central de Atendimento no on_ready (guild=%s).",
                    guild.id,
                )

    @tasks.loop(seconds=300)
    async def verificar_painel_permanente(self):
        for guild in self.bot.guilds:
            try:
                config = await get_config(guild.id)

                # Migra o menu padrão sem exigir comandos administrativos.
                if not config.get("ticket_modelo_v7"):
                    await tickets.set_tipos(
                        guild.id,
                        list(tickets.TIPOS_PADRAO),
                    )
                    await set_config(
                        guild.id,
                        ticket_modelo_v2=True,
                        ticket_modelo_v3=True,
                        ticket_modelo_v4=True,
                        ticket_modelo_v5=True,
                        ticket_modelo_v6=True,
                        ticket_modelo_v7=True,
                    )
                    config = await get_config(guild.id)

                canal_id = int(config.get("ticket_painel_canal_id") or TICKET_PAINEL_CANAL_ID)
                mensagem_id = config.get("ticket_painel_mensagem_id")
                canal = guild.get_channel(int(canal_id))
                if not isinstance(canal, discord.TextChannel):
                    continue

                view = await _montar_select(guild.id, guild)

                if mensagem_id:
                    try:
                        mensagem_existente = await canal.fetch_message(int(mensagem_id))
                        if mensagem_existente.embeds or not mensagem_existente.components:
                            await mensagem_existente.edit(
                                content=None, embed=None, embeds=[], attachments=[], view=view
                            )
                            log.info("Painel de atendimento migrado para Components V2 no canal %s.", canal.id)
                        continue
                    except discord.NotFound:
                        pass
                    except (discord.Forbidden, discord.HTTPException):
                        log.exception("Falha ao migrar painel de atendimento no canal %s.", canal.id)
                        continue

                mensagem = await canal.send(view=view)
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

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        info = tickets.parse_topic(channel.topic)
        if not info:
            return
        ULTIMA_ATIVIDADE.pop(channel.id, None)
        CANAIS_ESCALADOS.discard(channel.id)
        try:
            registro = await tickets.get_ticket_por_canal(channel.guild.id, channel.id)
            if registro and registro.get("status") == "fechando":
                await tickets.finalizar_fechamento_ticket(
                    channel.guild.id,
                    registro["id"],
                )
            elif registro and registro.get("status") == "aberto":
                await tickets.fechar_ticket(
                    channel.guild.id,
                    registro["id"],
                    motivo="Canal removido manualmente do servidor.",
                )
                log.info(
                    "Registro do ticket %s encerrado após exclusão manual do canal %s.",
                    registro.get("id"),
                    channel.id,
                )
        except Exception:
            log.exception(
                "Falha ao sincronizar exclusão do canal de ticket %s.",
                channel.id,
            )

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time()

        for guild in self.bot.guilds:
            try:
                todos_registros = await tickets.listar_tickets(guild.id)
                canais_registrados = {
                    str(item.get("canal_id"))
                    for item in todos_registros
                    if item.get("canal_id") is not None
                }

                for canal_candidato in guild.text_channels:
                    info = tickets.parse_topic(canal_candidato.topic)
                    if not info or str(canal_candidato.id) in canais_registrados:
                        continue
                    recuperado = await tickets.sincronizar_canal_ticket(
                        guild_id=guild.id,
                        canal_id=canal_candidato.id,
                        usuario_id=int(info.get("owner_id") or 0),
                        tipo=info.get("tipo") or "outro",
                    )
                    if recuperado:
                        ULTIMA_ATIVIDADE[canal_candidato.id] = float(
                            recuperado.get("criado_em") or agora
                        )
                        log.warning(
                            "Ticket órfão recuperado: guild=%s channel=%s ticket=%s",
                            guild.id,
                            canal_candidato.id,
                            recuperado.get("id"),
                        )

                fechando = await tickets.listar_tickets(
                    guild.id,
                    status="fechando",
                )
                for ticket_fechando in fechando:
                    try:
                        canal_fechando_id = int(ticket_fechando.get("canal_id") or 0)
                    except (TypeError, ValueError):
                        canal_fechando_id = 0
                    if not canal_fechando_id:
                        await tickets.finalizar_fechamento_ticket(
                            guild.id, ticket_fechando["id"]
                        )
                        continue
                    canal_fechando = guild.get_channel(canal_fechando_id)
                    if canal_fechando is None:
                        try:
                            canal_fechando = await guild.fetch_channel(canal_fechando_id)
                        except discord.NotFound:
                            await tickets.finalizar_fechamento_ticket(
                                guild.id, ticket_fechando["id"]
                            )
                            continue
                        except (discord.Forbidden, discord.HTTPException):
                            continue
                    if isinstance(canal_fechando, discord.TextChannel):
                        await fechar_canal_ticket(
                            canal_fechando,
                            ticket_fechando.get("motivo_fechamento") or "Retomando fechamento pendente.",
                            delay=0,
                            fechado_por_id=ticket_fechando.get("fechado_por_id"),
                        )

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
                        except discord.NotFound:
                            await tickets.fechar_ticket(
                                guild.id,
                                ticket["id"],
                                motivo="Canal do ticket removido.",
                            )
                            continue
                        except (discord.Forbidden, discord.HTTPException):
                            log.warning(
                                "Canal do ticket %s está inacessível; registro mantido para nova tentativa.",
                                canal_id,
                            )
                            continue

                    if not isinstance(canal, discord.TextChannel):
                        continue

                    ultima = ULTIMA_ATIVIDADE.get(canal.id)
                    if ultima is None:
                        # Recupera a última atividade humana do próprio histórico,
                        # em vez de reiniciar o prazo inteiro após cada restart.
                        ultima = float(ticket.get("ultima_atividade") or ticket.get("criado_em") or agora)
                        try:
                            async for mensagem_recente in canal.history(limit=100):
                                if not mensagem_recente.author.bot:
                                    ultima = mensagem_recente.created_at.timestamp()
                                    break
                        except (discord.Forbidden, discord.HTTPException):
                            log.warning(
                                "Não foi possível ler o histórico do ticket %s para recuperar a inatividade; prazo reiniciado por segurança.",
                                canal.id,
                            )
                            ultima = agora
                        ULTIMA_ATIVIDADE[canal.id] = ultima

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
