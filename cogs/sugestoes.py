from __future__ import annotations

import logging
import re
import time
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.apresentacao import criar_embed
from utils.guild_config import GUILD_NEMESIS_ID, membro_tem_lideranca
from utils.registro_global import registrar as registrar_global
from utils.storage import atualizar_json, carregar, salvar

_LOG = logging.getLogger(__name__)

CANAL_SUGESTOES_ID = 1563995881508831336
ARQUIVO_SUGESTOES = "sugestoes_nemesis.json"
ARQUIVO_COOLDOWN = "sugestoes_cooldown.json"
ARQUIVO_PAINEL = "sugestoes_painel.json"
ARQUIVO_SEGUIDORES = "sugestoes_seguidores.json"
COOLDOWN_SEGUNDOS = 600
LIMITE_DUPLICIDADE = 0.91
COR_SUGESTOES = 0x8B1E2D

CATEGORIAS = (
    "Sistemas",
    "Missões e operações",
    "Eventos",
    "Competitivo",
    "Comunidade",
    "Qualidade de vida",
    "Outros",
)
STATUS = {
    "pendente": ("⏳ Pendente", 0x8B1E2D),
    "analise": ("🔎 Em análise", 0x741629),
    "aprovada": ("✅ Aprovada", 0x991B33),
    "desenvolvimento": ("🛠️ Em desenvolvimento", 0x6B1729),
    "rejeitada": ("❌ Rejeitada", 0x5C101F),
    "implementada": ("🏆 Implementada", 0x381018),
}
STATUS_TERMINAIS = {"rejeitada", "implementada"}


def _normalizar_categoria(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").strip().casefold())
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    aliases = {
        "sistema": "Sistemas",
        "sistemas": "Sistemas",
        "missao": "Missões e operações",
        "missoes": "Missões e operações",
        "operacoes": "Missões e operações",
        "evento": "Eventos",
        "eventos": "Eventos",
        "pvp": "Competitivo",
        "competitivo": "Competitivo",
        "comunidade": "Comunidade",
        "qualidade de vida": "Qualidade de vida",
        "outros": "Outros",
    }
    return aliases.get(texto, "Outros")


def _normalizar_titulo(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def _encontrar_duplicada(registros: dict, titulo: str, ignorar_id: str | None = None) -> dict | None:
    alvo = _normalizar_titulo(titulo)
    if len(alvo) < 8:
        return None
    melhor = None
    melhor_indice = 0.0
    for item in registros.values() if isinstance(registros, dict) else ():
        if not isinstance(item, dict) or item.get("status") in STATUS_TERMINAIS:
            continue
        if ignorar_id is not None and str(item.get("id")) == str(ignorar_id):
            continue
        existente = _normalizar_titulo(item.get("titulo", ""))
        if not existente:
            continue
        indice = SequenceMatcher(None, alvo, existente).ratio()
        if alvo == existente:
            indice = 1.0
        if indice >= LIMITE_DUPLICIDADE and indice > melhor_indice:
            melhor = item
            melhor_indice = indice
    return melhor


def _registro_no_canal(interaction: discord.Interaction, registro: dict) -> bool:
    if not _esta_no_canal_sugestoes(interaction):
        return False
    canal = interaction.channel
    canal_registro = int(registro.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
    # Registros antigos podem guardar o ID do Fórum; os atuais guardam o ID
    # do tópico. Aceitamos ambos, mas nunca um canal fora do Fórum oficial.
    if isinstance(canal, discord.Thread):
        return canal_registro in {canal.id, canal.parent_id, CANAL_SUGESTOES_ID}
    return getattr(canal, "id", None) == canal_registro == CANAL_SUGESTOES_ID


async def _resolver_canal_publicacao(guild: discord.Guild, registro: dict):
    """Resolve publicações de Fórum e texto, inclusive registros legados/arquivados."""
    canal_id = int(registro.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
    mensagem_id = int(registro.get("id") or 0)
    thread_id = int(registro.get("thread_id") or 0)
    canal = guild.get_channel(canal_id) or guild.get_thread(canal_id)

    if isinstance(canal, discord.Thread):
        return canal

    if canal is None:
        try:
            canal = await guild.fetch_channel(canal_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            canal = None

    if isinstance(canal, discord.Thread):
        return canal

    if isinstance(canal, discord.ForumChannel):
        for thread in getattr(canal, "threads", []):
            if thread.id in {thread_id, mensagem_id}:
                return thread
        for candidato_id in (thread_id, mensagem_id):
            if not candidato_id:
                continue
            thread = guild.get_thread(candidato_id)
            if thread is None:
                try:
                    thread = await guild.fetch_channel(candidato_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    thread = None
            if isinstance(thread, discord.Thread) and thread.parent_id == canal.id:
                return thread
        try:
            async for thread in canal.archived_threads(limit=100):
                if thread.id in {thread_id, mensagem_id}:
                    return thread
        except (discord.Forbidden, discord.HTTPException):
            _LOG.debug("Não foi possível consultar tópicos arquivados do Fórum %s.", canal.id)
        return None

    if canal is None and canal_id != CANAL_SUGESTOES_ID:
        forum = guild.get_channel(CANAL_SUGESTOES_ID)
        if forum is None:
            try:
                forum = await guild.fetch_channel(CANAL_SUGESTOES_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                forum = None
        if isinstance(forum, discord.ForumChannel):
            return await _resolver_canal_publicacao(
                guild,
                {**registro, "canal_publicacao_id": forum.id},
            )
    return canal


async def _alternar_seguidor(message_id: str, usuario_id: int) -> bool:
    seguindo = False
    def atualizar(dados):
        nonlocal seguindo
        if not isinstance(dados, dict):
            dados = {}
        seguidores = set(str(item) for item in dados.get(str(message_id), []))
        chave = str(int(usuario_id))
        if chave in seguidores:
            seguidores.remove(chave)
            seguindo = False
        else:
            seguidores.add(chave)
            seguindo = True
        dados[str(message_id)] = sorted(seguidores)
        return dados
    await atualizar_json(ARQUIVO_SEGUIDORES, {}, atualizar)
    return seguindo


async def _listar_seguidores(message_id: str) -> list[int]:
    dados = await carregar(ARQUIVO_SEGUIDORES, {})
    itens = dados.get(str(message_id), []) if isinstance(dados, dict) else []
    resultado = []
    for item in itens if isinstance(itens, list) else []:
        try:
            resultado.append(int(item))
        except (TypeError, ValueError):
            continue
    return resultado


async def _notificar_atualizacao_sugestao(
    guild: discord.Guild,
    registro: dict,
    message_id: str,
    status: str,
    motivo: str,
) -> tuple[int, int]:
    """Notifica autor e seguidores opt-in; falha de DM nunca desfaz a decisão."""
    autor_id = int(registro.get("autor_id") or 0)
    destinatarios = set(await _listar_seguidores(message_id))
    if autor_id:
        destinatarios.add(autor_id)
    enviados = falhas = 0
    rotulo, cor = STATUS.get(status, STATUS["pendente"])
    embed = criar_embed(
        "📬 ATUALIZAÇÃO DA SUA SUGESTÃO",
        f"**{registro.get('titulo', 'Sugestão')}**\nSituação: **{rotulo}**\n\n{str(motivo)[:900]}",
        cor=cor,
        rodape="NÊMESIS • CENTRAL DE SUGESTÕES",
    )
    for membro_id in sorted(destinatarios):
        try:
            membro = guild.get_member(membro_id)
            if membro is None:
                membro = await guild.fetch_member(membro_id)
            await membro.send(embed=embed)
            enviados += 1
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            falhas += 1
            _LOG.info("DM de atualização indisponível para membro %s na sugestão %s.", membro_id, message_id)
        except Exception:
            falhas += 1
            _LOG.exception("Falha inesperada ao notificar membro %s da sugestão %s.", membro_id, message_id)
    return enviados, falhas


async def _editar_registro(message_id: str, autor_id: int, titulo: str, descricao: str, impacto: str) -> dict | None:
    resultado = None
    def atualizar(dados):
        nonlocal resultado
        if not isinstance(dados, dict):
            return dados
        atual = dados.get(str(message_id))
        if not isinstance(atual, dict) or int(atual.get("autor_id", 0)) != int(autor_id):
            return dados
        if atual.get("status") not in {"pendente", "analise"}:
            return dados
        atual = dict(atual)
        atual.update({
            "titulo": titulo.strip(),
            "descricao": descricao.strip(),
            "impacto": impacto.strip(),
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "editado_em": datetime.now(timezone.utc).isoformat(),
        })
        dados[str(message_id)] = atual
        resultado = dict(atual)
        return dados
    await atualizar_json(ARQUIVO_SUGESTOES, {}, atualizar)
    return resultado


def _esta_no_canal_sugestoes(interaction: discord.Interaction) -> bool:
    if interaction.guild_id != GUILD_NEMESIS_ID:
        return False
    canal = interaction.channel
    return bool(
        getattr(canal, "id", None) == CANAL_SUGESTOES_ID
        or (isinstance(canal, discord.Thread) and canal.parent_id == CANAL_SUGESTOES_ID)
    )


def _chave_mensagem(interaction: discord.Interaction) -> str:
    return str(getattr(interaction.message, "id", 0))


def _contagem_votos(votos: dict) -> tuple[int, int]:
    votos = votos if isinstance(votos, dict) else {}
    return (
        sum(1 for voto in votos.values() if voto == "apoia"),
        sum(1 for voto in votos.values() if voto == "nao_apoia"),
    )


def _registrar_voto(votos: dict, usuario_id: int, escolha: str) -> dict:
    """Registra um voto por pessoa; clicar novamente na mesma opção remove o voto."""
    resultado = dict(votos) if isinstance(votos, dict) else {}
    chave = str(int(usuario_id))
    if resultado.get(chave) == escolha:
        resultado.pop(chave, None)
    else:
        resultado[chave] = escolha
    return resultado


def _embed_painel() -> discord.Embed:
    embed = criar_embed(
        "💡 CENTRAL DE SUGESTÕES",
        (
            "Sua ideia pode ajudar a evoluir a NÊMESIS.\n\n"
            "**Como participar**\n"
            "1. Pressione **Enviar sugestão**.\n"
            "2. Informe um título, explique sua ideia e escolha uma categoria.\n"
            "3. A sugestão será publicada para a comunidade votar e comentar.\n"
            "4. Acompanhe as decisões diretamente na publicação.\n\n"
            "**Regras:** apresente ideias com respeito, evite duplicatas e não envie "
            "conteúdo ofensivo ou fora do propósito da organização.\n"
            "Cada membro pode enviar uma sugestão a cada 10 minutos."
        ),
        cor=COR_SUGESTOES,
        rodape="NÊMESIS • CENTRAL DE SUGESTÕES • PAINEL OFICIAL",
    )
    embed.add_field(
        name="◈ CATEGORIAS",
        value="Sistemas • Missões • Eventos • Competitivo • Comunidade • Qualidade de vida • Outros",
        inline=False,
    )
    embed.set_footer(text="NÊMESIS • CENTRAL DE SUGESTÕES • PAINEL OFICIAL")
    return embed


def _embed_sugestao(registro: dict) -> discord.Embed:
    status, cor = STATUS.get(registro.get("status", "pendente"), STATUS["pendente"])
    votos = registro.get("votos", {})
    apoios, oposicoes = _contagem_votos(votos)
    total = apoios + oposicoes
    aprovacao = round((apoios / total) * 100) if total else 0
    descricao = str(registro.get("descricao", ""))
    embed = criar_embed(
        f"💡 {str(registro.get('titulo', 'Sugestão'))[:240]}",
        descricao[:4096],
        cor=cor,
        rodape=f"NÊMESIS • SUGESTÃO #{registro.get('id', '—')}",
        timestamp=True,
    )
    embed.add_field(name="◈ AUTOR", value=f"<@{registro.get('autor_id')}>", inline=True)
    embed.add_field(name="◈ CATEGORIA", value=str(registro.get("categoria", "Outros"))[:100], inline=True)
    embed.add_field(name="◈ SITUAÇÃO", value=status, inline=True)
    try:
        criado = datetime.fromisoformat(str(registro.get("criado_em", "")))
        embed.timestamp = criado
    except (TypeError, ValueError):
        pass
    try:
        atualizado = datetime.fromisoformat(str(registro.get("atualizado_em", "")))
        embed.add_field(name="🕒 ÚLTIMA ATUALIZAÇÃO", value=f"<t:{int(atualizado.timestamp())}:R>", inline=True)
    except (TypeError, ValueError):
        pass
    impacto = str(registro.get("impacto", "")).strip()
    if impacto:
        embed.add_field(name="🎯 RESULTADO ESPERADO", value=impacto[:1024], inline=False)
    embed.add_field(name="👍 APOIO", value=str(apoios), inline=True)
    embed.add_field(name="👎 NÃO APOIO", value=str(oposicoes), inline=True)
    embed.add_field(name="📊 APROVAÇÃO", value=f"{aprovacao}% ({total} votos)", inline=True)
    motivo = registro.get("motivo_decisao")
    if motivo:
        embed.add_field(name="◈ POSICIONAMENTO DA LIDERANÇA", value=str(motivo)[:1024], inline=False)
    responsavel = registro.get("responsavel_id")
    if responsavel:
        embed.add_field(name="◈ RESPONSÁVEL PELA DECISÃO", value=f"<@{responsavel}>", inline=True)
    embed.set_footer(text=f"NÊMESIS • SUGESTÃO #{registro.get('id', '—')} • VOTAÇÃO COM 1 VOTO POR MEMBRO")
    return embed



def _card_sugestoes_view(origem: discord.ui.View, embed: discord.Embed | None = None,
                         titulo: str = "CENTRAL DE SUGESTÕES", descricao: str = "",
                         marcador: str = "NÊMESIS • SUGESTÕES • V2") -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    partes = [f"## {embed.title if embed and embed.title else titulo}"]
    if embed and embed.description:
        partes.append(embed.description)
    elif descricao:
        partes.append(descricao)
    if embed:
        for campo in embed.fields:
            partes.append(f"**{campo.name}**\n{campo.value}")
        if embed.image and embed.image.url:
            partes.append(f"[Abrir imagem anexada]({embed.image.url})")
        if embed.footer and embed.footer.text:
            partes.append(f"-# {embed.footer.text}")
    componentes = [
        discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    seletores, botoes = [], []
    for item in origem.children:
        if isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)
    for seletor in seletores:
        componentes.append(discord.ui.ActionRow(seletor))
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(f"-# {marcador}"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


def _mensagem_tem_cartao_sugestoes(mensagem: discord.Message, marcador: str) -> bool:
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        item = pendentes.pop()
        if marcador.casefold() in str(getattr(item, "content", "") or "").casefold():
            return True
        pendentes.extend(list(getattr(item, "children", []) or []))
    return False


async def _atualizar_cartao_sugestao(mensagem: discord.Message, registro: dict) -> None:
    embed = _embed_sugestao(registro)
    view = _card_sugestoes_view(
        PublicacaoSugestaoView(
            votacao_encerrada=registro.get("status") in STATUS_TERMINAIS,
            edicao_encerrada=registro.get("status") not in {"pendente", "analise"},
        ),
        embed,
        marcador="NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2",
    )
    if not _mensagem_tem_cartao_sugestoes(mensagem, "NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2"):
        await mensagem.edit(content=None, embeds=[], attachments=[])
    await mensagem.edit(view=view, allowed_mentions=discord.AllowedMentions.none())


async def _obter_registro(message_id: str) -> dict | None:
    dados = await carregar(ARQUIVO_SUGESTOES, {})
    item = dados.get(str(message_id)) if isinstance(dados, dict) else None
    return item if isinstance(item, dict) else None


async def _salvar_registro(message_id: str, registro: dict) -> None:
    def atualizar(dados):
        if not isinstance(dados, dict):
            dados = {}
        dados[str(message_id)] = registro
        return dados
    await atualizar_json(ARQUIVO_SUGESTOES, {}, atualizar)


async def _atualizar_voto(message_id: str, usuario_id: int, escolha: str) -> dict | None:
    resultado = None
    def atualizar(dados):
        nonlocal resultado
        if not isinstance(dados, dict):
            dados = {}
        atual = dados.get(str(message_id))
        if not isinstance(atual, dict):
            return dados
        if atual.get("status") in STATUS_TERMINAIS:
            resultado = {"encerrada": True, **atual}
            return dados
        atual = dict(atual)
        atual["votos"] = _registrar_voto(atual.get("votos", {}), usuario_id, escolha)
        atual["atualizado_em"] = datetime.now(timezone.utc).isoformat()
        dados[str(message_id)] = atual
        resultado = dict(atual)
        return dados
    await atualizar_json(ARQUIVO_SUGESTOES, {}, atualizar)
    return resultado


async def _atualizar_decisao(
    message_id: str,
    status: str,
    motivo: str,
    responsavel_id: int,
) -> dict | None:
    if status not in STATUS:
        return None
    resultado = None
    def atualizar(dados):
        nonlocal resultado
        if not isinstance(dados, dict):
            dados = {}
        atual = dados.get(str(message_id))
        if not isinstance(atual, dict):
            return dados
        atual = dict(atual)
        agora = datetime.now(timezone.utc).isoformat()
        historico = list(atual.get("historico_status", []))
        historico.append({
            "de": atual.get("status", "pendente"),
            "para": status,
            "motivo": motivo.strip(),
            "responsavel_id": int(responsavel_id),
            "em": agora,
        })
        atual.update({
            "status": status,
            "motivo_decisao": motivo.strip(),
            "responsavel_id": int(responsavel_id),
            "historico_status": historico[-30:],
            "atualizado_em": agora,
        })
        dados[str(message_id)] = atual
        resultado = dict(atual)
        return dados
    await atualizar_json(ARQUIVO_SUGESTOES, {}, atualizar)
    return resultado


async def _reservar_cooldown(usuario_id: int, agora: int) -> int:
    """Reserva atomicamente o intervalo de envio; retorna segundos restantes."""
    restante = 0
    def atualizar(dados):
        nonlocal restante
        if not isinstance(dados, dict):
            dados = {}
        chave = str(int(usuario_id))
        ultimo = int(dados.get(chave, 0) or 0)
        restante = max(0, COOLDOWN_SEGUNDOS - (agora - ultimo))
        if restante == 0:
            dados[chave] = int(agora)
        return dados
    await atualizar_json(ARQUIVO_COOLDOWN, {}, atualizar)
    return restante


async def _liberar_cooldown(usuario_id: int, reserva: int) -> None:
    def atualizar(dados):
        if not isinstance(dados, dict):
            return {}
        chave = str(int(usuario_id))
        if int(dados.get(chave, 0) or 0) == int(reserva):
            dados.pop(chave, None)
        return dados
    await atualizar_json(ARQUIVO_COOLDOWN, {}, atualizar)


class ModalNovaSugestao(discord.ui.Modal, title="Enviar uma sugestão"):
    titulo = discord.ui.TextInput(
        label="Título da ideia",
        placeholder="Resuma sua sugestão em poucas palavras",
        min_length=5,
        max_length=100,
    )
    descricao = discord.ui.TextInput(
        label="Explique sua sugestão",
        placeholder="Qual é a ideia? Como ela ajudaria a NÊMESIS?",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=1800,
    )
    impacto = discord.ui.TextInput(
        label="Resultado esperado",
        placeholder="Que melhoria concreta essa ideia traria?",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=500,
    )
    categoria = discord.ui.TextInput(
        label="Categoria",
        placeholder="Ex.: Sistemas, Eventos, Comunidade...",
        max_length=40,
        default="Comunidade",
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not _esta_no_canal_sugestoes(interaction) or interaction.user.bot:
            await interaction.response.send_message("Este formulário só funciona para membros no canal oficial de sugestões.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registros_atuais = await carregar(ARQUIVO_SUGESTOES, {})
            duplicada = _encontrar_duplicada(registros_atuais, self.titulo.value)
            if duplicada:
                canal_id = int(duplicada.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
                mensagem_id = duplicada.get("id")
                link = f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{canal_id}/{mensagem_id}"
                await interaction.followup.send(
                    f"Encontrei uma sugestão muito parecida com essa ideia: [ver publicação existente]({link}). "
                    "Vote ou comente nela para fortalecer a proposta, em vez de criar uma duplicata.",
                    ephemeral=True,
                )
                return
        except Exception:
            _LOG.exception("Falha ao verificar sugestões duplicadas.")
            await interaction.followup.send("Não consegui verificar sugestões existentes. Tente novamente em instantes.", ephemeral=True)
            return
        agora = int(time.time())
        try:
            restante = await _reservar_cooldown(interaction.user.id, agora)
        except Exception:
            _LOG.exception("Falha ao reservar cooldown de sugestão para %s.", interaction.user.id)
            await interaction.followup.send("O armazenamento está indisponível no momento. Tente novamente mais tarde.", ephemeral=True)
            return
        if restante > 0:
            await interaction.followup.send(
                f"Você poderá enviar outra sugestão em **{restante // 60} min {restante % 60} s**.",
                ephemeral=True,
            )
            return

        categoria = _normalizar_categoria(self.categoria.value)
        canal = interaction.guild.get_channel(CANAL_SUGESTOES_ID)
        if canal is None:
            try:
                canal = await interaction.guild.fetch_channel(CANAL_SUGESTOES_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal = None
        if not isinstance(canal, (discord.TextChannel, discord.ForumChannel)):
            await _liberar_cooldown(interaction.user.id, agora)
            await interaction.followup.send("O canal oficial de sugestões não está disponível ou não é um canal compatível.", ephemeral=True)
            return

        registro = {
            "id": None,
            "autor_id": interaction.user.id,
            "titulo": str(self.titulo.value).strip(),
            "descricao": str(self.descricao.value).strip(),
            "impacto": str(self.impacto.value).strip(),
            "categoria": categoria,
            "status": "pendente",
            "votos": {},
            "motivo_decisao": None,
            "responsavel_id": None,
            "criado_em": datetime.now(timezone.utc).isoformat(),
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "thread_id": None,
            "canal_publicacao_id": canal.id,
        }
        mensagem = None
        persistida = False
        try:
            if isinstance(canal, discord.ForumChannel):
                thread, mensagem = await canal.create_thread(
                    name=f"💡・{registro['titulo']}"[:100],
                    view=_card_sugestoes_view(
                        PublicacaoSugestaoView(), _embed_sugestao(registro),
                        marcador="NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2",
                    ),
                    reason="Nova sugestão enviada pela comunidade",
                )
                registro["canal_publicacao_id"] = thread.id
            else:
                mensagem = await canal.send(
                    view=_card_sugestoes_view(
                        PublicacaoSugestaoView(), _embed_sugestao(registro),
                        marcador="NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2",
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            registro["id"] = mensagem.id
            await _atualizar_cartao_sugestao(mensagem, registro)
            await _salvar_registro(str(mensagem.id), registro)
            persistida = True

            await registrar_global(
                interaction.guild,
                "sugestoes",
                "Nova sugestão recebida",
                f"**{registro['titulo']}**\nAutor: {interaction.user.mention}\nCategoria: {categoria}\n[Publicação](https://discord.com/channels/{interaction.guild.id}/{registro['canal_publicacao_id']}/{mensagem.id})",
                cor=COR_SUGESTOES,
            )
            await interaction.followup.send(
                f"Sua sugestão foi publicada: {mensagem.jump_url}",
                ephemeral=True,
            )
        except Exception:
            _LOG.exception("Falha ao publicar sugestão (guild=%s, user=%s).", interaction.guild_id, interaction.user.id)
            if not persistida:
                await _liberar_cooldown(interaction.user.id, agora)
                if mensagem is not None:
                    try:
                        await mensagem.delete(reason="Falha ao persistir os dados da sugestão")
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        _LOG.warning("Não foi possível remover publicação sem registro %s.", mensagem.id)
                resposta = "Não foi possível publicar sua sugestão agora. Tente novamente em instantes."
            else:
                resposta = f"Sua sugestão foi publicada: {mensagem.jump_url}"
            await interaction.followup.send(resposta, ephemeral=True)


class PainelSugestoesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enviar sugestão",
        emoji="💡",
        style=discord.ButtonStyle.danger,
        custom_id="nemesis:sugestoes:enviar",
    )
    async def enviar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _esta_no_canal_sugestoes(interaction):
            await interaction.response.send_message("Use o painel no canal oficial da NÊMESIS.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalNovaSugestao())




    @discord.ui.button(
        label="Painel da liderança",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="nemesis:sugestoes:painel_admin",
    )
    async def painel_lideranca(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_NEMESIS_ID or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registros = await carregar(ARQUIVO_SUGESTOES, {})
            if not isinstance(registros, dict):
                registros = {}
            await interaction.edit_original_response(
                view=_card_sugestoes_view(
                    PainelAdminSugestoesView(registros),
                    _embed_painel_administrativo(registros),
                    marcador="NÊMESIS • PAINEL ADMINISTRATIVO DE SUGESTÕES • V2",
                ),
            )
        except Exception:
            _LOG.exception("Falha ao abrir painel administrativo de sugestões.")
            await interaction.edit_original_response(content="Não foi possível carregar o painel agora.", embed=None, view=None)

def _embed_painel_administrativo(registros: dict, filtro: str = "resumo") -> discord.Embed:
    itens = [item for item in registros.values() if isinstance(item, dict)]
    contagens = {
        chave: sum(1 for item in itens if item.get("status") == chave)
        for chave in STATUS
    }
    embed = criar_embed(
        "📊 CENTRAL DE SUGESTÕES • LIDERANÇA",
        "Acompanhamento interno das propostas recebidas pela NÊMESIS.",
        cor=COR_SUGESTOES,
        rodape="NÊMESIS • PAINEL ADMINISTRATIVO DE SUGESTÕES",
    )
    embed.add_field(name="📥 TOTAL RECEBIDO", value=str(len(itens)), inline=True)
    embed.add_field(name="⏳ PENDENTES", value=str(contagens["pendente"]), inline=True)
    embed.add_field(name="🔎 EM ANÁLISE", value=str(contagens["analise"]), inline=True)
    embed.add_field(name="✅ APROVADAS", value=str(contagens["aprovada"]), inline=True)
    embed.add_field(name="❌ REJEITADAS", value=str(contagens["rejeitada"]), inline=True)
    embed.add_field(name="🛠️ EM DESENVOLVIMENTO", value=str(contagens["desenvolvimento"]), inline=True)
    embed.add_field(name="🏆 IMPLEMENTADAS", value=str(contagens["implementada"]), inline=True)
    votos_totais = sum(sum(_contagem_votos(item.get("votos", {}))) for item in itens)
    decididas = sum(contagens[chave] for chave in ("aprovada", "desenvolvimento", "implementada", "rejeitada"))
    favoraveis = contagens["aprovada"] + contagens["desenvolvimento"] + contagens["implementada"]
    taxa = round(favoraveis * 100 / decididas) if decididas else 0
    embed.add_field(name="🗳️ VOTOS REGISTRADOS", value=str(votos_totais), inline=True)
    embed.add_field(name="📈 TAXA DE APROVAÇÃO", value=f"{taxa}% ({decididas} decisões)", inline=True)

    if filtro == "populares":
        selecionados = sorted(
            itens,
            key=lambda item: (_contagem_votos(item.get("votos", {}))[0], -_contagem_votos(item.get("votos", {}))[1]),
            reverse=True,
        )[:10]
        titulo = "🔥 SUGESTÕES MAIS APOIADAS"
    elif filtro in STATUS:
        selecionados = [item for item in itens if item.get("status") == filtro]
        selecionados.sort(key=lambda item: item.get("atualizado_em", ""), reverse=True)
        selecionados = selecionados[:10]
        titulo = f"{STATUS[filtro][0].upper()} • ATÉ 10 REGISTROS"
    else:
        selecionados = sorted(itens, key=lambda item: item.get("criado_em", ""), reverse=True)[:10]
        titulo = "🕒 ATIVIDADE RECENTE"

    if selecionados:
        linhas = []
        for item in selecionados:
            apoios, oposicoes = _contagem_votos(item.get("votos", {}))
            message_id = item.get("id")
            link = (
                f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{item.get('canal_publicacao_id', CANAL_SUGESTOES_ID)}/{message_id}"
                if message_id else None
            )
            nome = discord.utils.escape_markdown(str(item.get("titulo", "Sugestão"))[:90])
            rotulo = f"[{nome}]({link})" if link else nome
            linhas.append(
                f"• {rotulo} — 👍 {apoios} / 👎 {oposicoes} — {STATUS.get(item.get('status'), STATUS['pendente'])[0]}"
            )
        embed.add_field(name=titulo, value="\n".join(linhas)[:1024], inline=False)
    else:
        embed.add_field(name=titulo, value="Nenhuma sugestão encontrada nesta seleção.", inline=False)
    return embed


class PainelAdminSugestoesView(discord.ui.View):
    def __init__(self, registros: dict):
        super().__init__(timeout=180)
        self.registros = registros
        seletor = discord.ui.Select(
            placeholder="Filtrar sugestões",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Atividade recente", value="resumo", emoji="🕒"),
                discord.SelectOption(label="Mais apoiadas", value="populares", emoji="🔥"),
                discord.SelectOption(label="Pendentes", value="pendente", emoji="⏳"),
                discord.SelectOption(label="Em análise", value="analise", emoji="🔎"),
                discord.SelectOption(label="Aprovadas", value="aprovada", emoji="✅"),
                discord.SelectOption(label="Em desenvolvimento", value="desenvolvimento", emoji="🛠️"),
                discord.SelectOption(label="Rejeitadas", value="rejeitada", emoji="❌"),
                discord.SelectOption(label="Implementadas", value="implementada", emoji="🏆"),
            ],
            custom_id="nemesis:sugestoes:painel_admin:filtro",
        )
        seletor.callback = self._filtrar
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != GUILD_NEMESIS_ID or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return False
        return True

    async def _filtrar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            registros = await carregar(ARQUIVO_SUGESTOES, {})
            self.registros = registros if isinstance(registros, dict) else {}
            await interaction.edit_original_response(
                view=_card_sugestoes_view(
                    self,
                    _embed_painel_administrativo(self.registros, self.children[0].values[0]),
                    marcador="NÊMESIS • PAINEL ADMINISTRATIVO DE SUGESTÕES • V2",
                ),
            )
        except Exception:
            _LOG.exception("Falha ao atualizar filtro do painel de sugestões.")
            await interaction.edit_original_response(content="Não foi possível atualizar os dados agora.", embed=None, view=None)





class PublicacaoSugestaoView(discord.ui.View):
    def __init__(self, *, votacao_encerrada: bool = False, edicao_encerrada: bool = False):
        super().__init__(timeout=None)
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id in {"nemesis:sugestoes:votar:apoia", "nemesis:sugestoes:votar:nao_apoia"}:
                item.disabled = votacao_encerrada
            elif item.custom_id == "nemesis:sugestoes:editar":
                item.disabled = edicao_encerrada

    @discord.ui.button(
        label="Apoiar",
        emoji="👍",
        style=discord.ButtonStyle.success,
        custom_id="nemesis:sugestoes:votar:apoia",
    )
    async def apoiar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._votar(interaction, "apoia")

    @discord.ui.button(
        label="Não apoiar",
        emoji="👎",
        style=discord.ButtonStyle.secondary,
        custom_id="nemesis:sugestoes:votar:nao_apoia",
    )
    async def nao_apoiar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._votar(interaction, "nao_apoia")

    @discord.ui.button(
        label="Comentar",
        emoji="💬",
        style=discord.ButtonStyle.secondary,
        custom_id="nemesis:sugestoes:comentar",
    )
    async def comentar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message is None or interaction.user.bot:
            await interaction.response.send_message("Esta ação só está disponível para membros da NÊMESIS.", ephemeral=True)
            return
        message_id = _chave_mensagem(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro = await _obter_registro(message_id)
            if not registro or not _registro_no_canal(interaction, registro):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
        except Exception:
            _LOG.exception("Falha ao carregar sugestão para abrir discussão %s.", message_id)
            await interaction.followup.send("Não foi possível carregar esta sugestão agora.", ephemeral=True)
            return
        thread = None
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.parent_id == CANAL_SUGESTOES_ID:
            thread = interaction.channel
        else:
            thread_id = registro.get("thread_id")
            if thread_id:
                thread = interaction.guild.get_thread(int(thread_id))
                if thread is None:
                    try:
                        thread = await interaction.guild.fetch_channel(int(thread_id))
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        thread = None
            if thread is None:
                try:
                    thread = await interaction.message.create_thread(
                        name=f"Discussão • {registro.get('titulo', 'Sugestão')}"[:100],
                        auto_archive_duration=10080,
                        reason="Criar discussão pública para sugestão da comunidade",
                    )
                    registro["thread_id"] = thread.id
                    await _salvar_registro(message_id, registro)
                except discord.HTTPException:
                    await interaction.followup.send("Não consegui abrir a discussão desta sugestão.", ephemeral=True)
                    return
        await interaction.followup.send(f"Participe da discussão: {thread.mention}", ephemeral=True)

    @discord.ui.button(
        label="Acompanhar",
        emoji="🔔",
        style=discord.ButtonStyle.secondary,
        custom_id="nemesis:sugestoes:acompanhar",
        row=1,
    )
    async def acompanhar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message is None or interaction.user.bot:
            await interaction.response.send_message("Acompanhar está disponível apenas para membros.", ephemeral=True)
            return
        message_id = _chave_mensagem(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro = await _obter_registro(message_id)
            if not registro or not _registro_no_canal(interaction, registro):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
            seguindo = await _alternar_seguidor(message_id, interaction.user.id)
            texto = "Você receberá atualizações desta sugestão por mensagem privada." if seguindo else "Você deixou de acompanhar esta sugestão."
            await interaction.followup.send(texto, ephemeral=True)
        except Exception:
            _LOG.exception("Falha ao alterar acompanhamento da sugestão %s.", message_id)
            await interaction.followup.send("Não foi possível alterar seu acompanhamento agora.", ephemeral=True)

    @discord.ui.button(
        label="Editar minha sugestão",
        emoji="✏️",
        style=discord.ButtonStyle.secondary,
        custom_id="nemesis:sugestoes:editar",
        row=1,
    )
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message is None or interaction.user.bot:
            await interaction.response.send_message("Edição disponível apenas para membros.", ephemeral=True)
            return
        registro = await _obter_registro(_chave_mensagem(interaction))
        if not registro or not _registro_no_canal(interaction, registro):
            await interaction.response.send_message("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
            return
        if int(registro.get("autor_id", 0)) != interaction.user.id:
            await interaction.response.send_message("Somente o autor pode editar esta sugestão.", ephemeral=True)
            return
        if registro.get("status") not in {"pendente", "analise"}:
            await interaction.response.send_message("Esta sugestão não pode mais ser editada após a decisão da liderança.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalEditarSugestao(_chave_mensagem(interaction), registro))

    @discord.ui.button(
        label="Gerenciar",
        emoji="⚙️",
        style=discord.ButtonStyle.danger,
        custom_id="nemesis:sugestoes:gerenciar",
    )
    async def gerenciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_NEMESIS_ID or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro = await _obter_registro(_chave_mensagem(interaction))
            if not registro or not _registro_no_canal(interaction, registro):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
            await interaction.edit_original_response(
                view=_card_sugestoes_view(
                    MenuDecisaoSugestaoView(_chave_mensagem(interaction)),
                    None, "GESTÃO DA SUGESTÃO",
                    "Selecione a situação administrativa que será registrada.",
                ),
            )
        except Exception:
            _LOG.exception("Falha ao abrir gestão da sugestão %s.", _chave_mensagem(interaction))
            await interaction.edit_original_response(content="Não foi possível carregar a gestão desta sugestão.", view=None)

    async def _votar(self, interaction: discord.Interaction, escolha: str):
        if interaction.message is None or interaction.user.bot:
            await interaction.response.send_message("Esta votação está disponível apenas para membros.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro_atual = await _obter_registro(_chave_mensagem(interaction))
            if not registro_atual or not _registro_no_canal(interaction, registro_atual):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
            if int(registro_atual.get("autor_id", 0)) == interaction.user.id:
                await interaction.followup.send("O autor não pode votar na própria sugestão.", ephemeral=True)
                return
            registro = await _atualizar_voto(_chave_mensagem(interaction), interaction.user.id, escolha)
            if not registro:
                await interaction.followup.send("Não encontrei os dados desta sugestão.", ephemeral=True)
                return
            if registro.get("encerrada"):
                await interaction.followup.send("A votação desta sugestão foi encerrada.", ephemeral=True)
                return
            await _atualizar_cartao_sugestao(interaction.message, registro)
            apoios, oposicoes = _contagem_votos(registro.get("votos", {}))
            await interaction.followup.send(
                f"Voto atualizado. 👍 **{apoios}** • 👎 **{oposicoes}**",
                ephemeral=True,
            )
        except Exception:
            _LOG.exception("Falha ao registrar voto na sugestão %s.", _chave_mensagem(interaction))
            await interaction.followup.send("Não foi possível atualizar seu voto agora.", ephemeral=True)


class ModalEditarSugestao(discord.ui.Modal, title="Editar minha sugestão"):
    titulo = discord.ui.TextInput(
        label="Título da ideia",
        min_length=5,
        max_length=100,
    )
    descricao = discord.ui.TextInput(
        label="Descrição atualizada",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=1800,
    )
    impacto = discord.ui.TextInput(
        label="Resultado esperado",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=500,
    )

    def __init__(self, message_id: str, registro: dict):
        super().__init__()
        self.message_id = str(message_id)
        self.titulo.default = str(registro.get("titulo", ""))[:100]
        self.descricao.default = str(registro.get("descricao", ""))[:1800]
        self.impacto.default = str(registro.get("impacto", ""))[:500] or "Melhorar a experiência da comunidade."

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.bot or not _esta_no_canal_sugestoes(interaction):
            await interaction.response.send_message("Edição disponível apenas na Central de Sugestões.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro_atual = await _obter_registro(self.message_id)
            if not registro_atual or not _registro_no_canal(interaction, registro_atual):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
            todos_registros = await carregar(ARQUIVO_SUGESTOES, {})
            duplicada = _encontrar_duplicada(todos_registros, str(self.titulo.value), ignorar_id=self.message_id)
            if duplicada:
                canal_duplicado = int(duplicada.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
                link_duplicado = f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{canal_duplicado}/{duplicada.get('id')}"
                await interaction.followup.send(
                    f"Esse título se parece com outra proposta ativa: [abrir sugestão existente]({link_duplicado}).",
                    ephemeral=True,
                )
                return
            registro = await _editar_registro(
                self.message_id,
                interaction.user.id,
                str(self.titulo.value),
                str(self.descricao.value),
                str(self.impacto.value),
            )
            if not registro:
                await interaction.followup.send("A sugestão não existe, não pertence a você ou já saiu da fila de edição.", ephemeral=True)
                return
            canal_id = int(registro.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
            canal = interaction.guild.get_channel(canal_id) or interaction.guild.get_thread(canal_id)
            if canal is None:
                canal = await interaction.guild.fetch_channel(canal_id)
            mensagem = await canal.fetch_message(int(self.message_id))
            await _atualizar_cartao_sugestao(mensagem, registro)
            if isinstance(canal, discord.Thread) and canal.parent_id == CANAL_SUGESTOES_ID:
                await canal.edit(name=f"💡・{registro['titulo']}"[:100], reason="Autor atualizou a própria sugestão")
            await registrar_global(
                interaction.guild,
                "sugestoes",
                "Sugestão editada pelo autor",
                f"**{registro['titulo']}**\nAutor: {interaction.user.mention}\n[Publicação]({mensagem.jump_url})",
                cor=COR_SUGESTOES,
            )
            await interaction.followup.send("Sua sugestão foi atualizada com sucesso.", ephemeral=True)
        except Exception:
            _LOG.exception("Falha ao editar sugestão %s.", self.message_id)
            await interaction.followup.send("Não foi possível atualizar sua sugestão agora.", ephemeral=True)


class MenuDecisaoSugestaoView(discord.ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=180)
        self.message_id = str(message_id)
        seletor = discord.ui.Select(
            placeholder="Escolha a situação da sugestão",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=STATUS[chave][0], value=chave, description=descricao)
                for chave, descricao in (
                    ("pendente", "Retornar para a fila de sugestões"),
                    ("analise", "A equipe está avaliando a proposta"),
                    ("aprovada", "A proposta foi aprovada e aguarda execução"),
                    ("desenvolvimento", "A equipe está trabalhando na proposta"),
                    ("rejeitada", "A proposta não será adotada"),
                    ("implementada", "A proposta já foi implementada"),
                )
            ],
            custom_id="nemesis:sugestoes:decisao:status",
        )
        seletor.callback = self._selecionar
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != GUILD_NEMESIS_ID or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return False
        return True

    async def _selecionar(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ModalDecisaoSugestao(self.message_id, self.children[0].values[0]))


class ModalDecisaoSugestao(discord.ui.Modal, title="Registrar decisão da liderança"):
    motivo = discord.ui.TextInput(
        label="Justificativa ou atualização",
        placeholder="Explique a decisão ou informe o andamento da proposta.",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=900,
    )

    def __init__(self, message_id: str, status: str):
        super().__init__()
        self.message_id = str(message_id)
        self.status = status

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_NEMESIS_ID or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro_existente = await _obter_registro(self.message_id)
            if not registro_existente or not _registro_no_canal(interaction, registro_existente):
                await interaction.followup.send("Esta publicação não pertence à Central de Sugestões.", ephemeral=True)
                return
            registro = await _atualizar_decisao(
                self.message_id,
                self.status,
                str(self.motivo.value),
                interaction.user.id,
            )
            if not registro:
                await interaction.followup.send("Não encontrei os dados desta sugestão.", ephemeral=True)
                return
            canal_id = int(registro.get("canal_publicacao_id", CANAL_SUGESTOES_ID))
            canal = interaction.guild.get_channel(canal_id) or interaction.guild.get_thread(canal_id)
            if canal is None:
                canal = await interaction.guild.fetch_channel(canal_id)
            mensagem = await canal.fetch_message(int(self.message_id))
            await _atualizar_cartao_sugestao(mensagem, registro)

            enviados, falhas_dm = await _notificar_atualizacao_sugestao(
                interaction.guild, registro, self.message_id, self.status, str(self.motivo.value)
            )
            _LOG.info(
                "Notificações da sugestão %s: %s enviadas, %s indisponíveis.",
                self.message_id, enviados, falhas_dm,
            )

            await registrar_global(
                interaction.guild,
                "sugestoes",
                "Decisão sobre sugestão",
                (
                    f"**{registro['titulo']}**\n"
                    f"Situação: {STATUS[self.status][0]}\n"
                    f"Responsável: {interaction.user.mention}\n"
                    f"Justificativa: {self.motivo.value}\n"
                    f"Votos: 👍 {_contagem_votos(registro.get('votos', {}))[0]} • "
                    f"👎 {_contagem_votos(registro.get('votos', {}))[1]}"
                ),
                cor=STATUS[self.status][1],
            )
            await interaction.followup.send("Decisão registrada e publicação atualizada.", ephemeral=True)
        except Exception:
            _LOG.exception("Falha ao aplicar decisão da sugestão %s.", self.message_id)
            await interaction.followup.send("Não foi possível concluir a decisão agora.", ephemeral=True)


class Sugestoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._painel_pronto = False
        self.bot.add_view(PainelSugestoesView())
        self.bot.add_view(PublicacaoSugestaoView())

    async def _sincronizar_publicacoes_existentes(self, guild: discord.Guild) -> int:
        """Atualiza controles de publicações antigas sem reenviar mensagens."""
        dados = await carregar(ARQUIVO_SUGESTOES, {})
        if not isinstance(dados, dict):
            return 0
        itens = [item for item in dados.values() if isinstance(item, dict)]
        itens.sort(key=lambda item: str(item.get("criado_em", "")), reverse=True)
        atualizadas = 0
        ignoradas = 0
        for registro in itens[:250]:
            try:
                mensagem_id = int(registro.get("id") or 0)
                if not mensagem_id:
                    ignoradas += 1
                    continue
                canal = await _resolver_canal_publicacao(guild, registro)
                if canal is None or not hasattr(canal, "fetch_message"):
                    ignoradas += 1
                    _LOG.debug("Publicação antiga %s sem canal recuperável; registro preservado.", mensagem_id)
                    continue
                try:
                    mensagem = await canal.fetch_message(mensagem_id)
                except discord.NotFound:
                    if isinstance(canal, discord.ForumChannel):
                        thread = await _resolver_canal_publicacao(guild, {**registro, "thread_id": mensagem_id})
                        if thread is None:
                            ignoradas += 1
                            continue
                        canal = thread
                        mensagem = await canal.fetch_message(mensagem_id)
                    else:
                        raise
                if _mensagem_tem_cartao_sugestoes(
                    mensagem, "NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2"
                ):
                    continue
                await _atualizar_cartao_sugestao(mensagem, registro)
                atualizadas += 1
            except discord.NotFound:
                ignoradas += 1
                _LOG.debug("Publicação antiga %s não existe mais no Discord; registro preservado.", registro.get("id"))
            except (discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                ignoradas += 1
                _LOG.warning(
                    "Não foi possível atualizar os botões da sugestão antiga %s.",
                    registro.get("id"),
                    exc_info=True,
                )
            except Exception:
                _LOG.exception(
                    "Falha inesperada ao migrar controles da sugestão antiga %s.",
                    registro.get("id"),
                )
        _LOG.info(
            "Controles das sugestões existentes sincronizados: %s atualizadas, %s ignoradas sem exclusão (lote máximo 250).",
            atualizadas,
            ignoradas,
        )
        return atualizadas

    async def _sincronizar_painel(self, guild: discord.Guild):
        canal = guild.get_channel(CANAL_SUGESTOES_ID)
        if canal is None:
            canal = await guild.fetch_channel(CANAL_SUGESTOES_ID)
        if not isinstance(canal, (discord.TextChannel, discord.ForumChannel)) or canal.guild.id != GUILD_NEMESIS_ID:
            raise TypeError("O canal oficial de sugestões não é um canal de texto ou Fórum da NÊMESIS.")

        dados = await carregar(ARQUIVO_PAINEL, {})
        mensagem = None
        destino = None
        salvo = dados.get(str(guild.id)) if isinstance(dados, dict) else None
        if salvo:
            try:
                if isinstance(canal, discord.ForumChannel):
                    destino = guild.get_thread(int(salvo))
                    if destino is None:
                        destino = await guild.fetch_channel(int(salvo))
                    if isinstance(destino, discord.Thread):
                        if destino.archived or destino.locked:
                            await destino.edit(archived=False, locked=False, reason="Atualizar painel oficial de sugestões")
                        mensagem = await destino.fetch_message(destino.id)
                else:
                    mensagem = await canal.fetch_message(int(salvo))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                mensagem = None
                destino = None

        if mensagem is None and isinstance(canal, discord.ForumChannel):
            existentes = list(canal.threads)
            try:
                async for thread in canal.archived_threads(limit=100):
                    if all(item.id != thread.id for item in existentes):
                        existentes.append(thread)
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception("Não foi possível consultar publicações arquivadas do Fórum de sugestões.")
            for thread in existentes:
                if thread.name == "💡・Central de Sugestões":
                    destino = thread
                    if destino.archived or destino.locked:
                        await destino.edit(archived=False, locked=False, reason="Atualizar painel oficial de sugestões")
                    mensagem = await destino.fetch_message(destino.id)
                    break

        if mensagem is None and isinstance(canal, discord.TextChannel):
            async for candidata in canal.history(limit=100, oldest_first=True):
                if candidata.author.id == self.bot.user.id and any(
                    embed.footer.text == "NÊMESIS • CENTRAL DE SUGESTÕES • PAINEL OFICIAL"
                    for embed in candidata.embeds
                ):
                    mensagem = candidata
                    break

        if mensagem is None and isinstance(canal, discord.ForumChannel):
            embed_painel = _embed_painel()
            destino, mensagem = await canal.create_thread(
                name="💡・Central de Sugestões",
                view=_card_sugestoes_view(
                    PainelSugestoesView(), embed_painel,
                    marcador="NÊMESIS • CENTRAL DE SUGESTÕES • V2",
                ),
                reason="Publicar painel oficial da Central de Sugestões",
            )
        elif mensagem is None:
            embed_painel = _embed_painel()
            mensagem = await canal.send(
                view=_card_sugestoes_view(
                    PainelSugestoesView(), embed_painel,
                    marcador="NÊMESIS • CENTRAL DE SUGESTÕES • V2",
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            embed_painel = _embed_painel()
            view_painel = _card_sugestoes_view(
                PainelSugestoesView(), embed_painel,
                marcador="NÊMESIS • CENTRAL DE SUGESTÕES • V2",
            )
            if not _mensagem_tem_cartao_sugestoes(
                mensagem, "NÊMESIS • CENTRAL DE SUGESTÕES • V2"
            ):
                await mensagem.edit(content=None, embeds=[], attachments=[])
            await mensagem.edit(
                view=view_painel,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        if isinstance(canal, discord.ForumChannel) and not mensagem.pinned:
            try:
                await mensagem.pin(reason="Manter destacado o painel oficial de sugestões")
            except (discord.Forbidden, discord.HTTPException):
                _LOG.warning("O painel foi publicado, mas não pôde ser fixado no Fórum de sugestões.")
        identificador = destino.id if isinstance(canal, discord.ForumChannel) and destino is not None else mensagem.id
        await salvar(ARQUIVO_PAINEL, {str(guild.id): identificador})
        _LOG.info("Painel oficial de sugestões sincronizado no canal %s (destino=%s).", canal.id, identificador)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._painel_pronto:
            return
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            _LOG.error("Servidor NÊMESIS indisponível; painel de sugestões aguardando conexão.")
            return
        try:
            await self._sincronizar_painel(guild)
            await self._sincronizar_publicacoes_existentes(guild)
            self._painel_pronto = True
        except Exception:
            _LOG.exception("Não foi possível sincronizar o painel oficial de sugestões.")


async def setup(bot: commands.Bot):
    bot.add_view(_card_sugestoes_view(
        PublicacaoSugestaoView(), None, "PUBLICAÇÃO DE SUGESTÃO",
        "Painel oficial de votação da NÊMESIS.",
        marcador="NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2",
    ))
    bot.add_view(_card_sugestoes_view(
        PainelSugestoesView(), _embed_painel(),
        marcador="NÊMESIS • CENTRAL DE SUGESTÕES • V2",
    ))
    await bot.add_cog(Sugestoes(bot))

