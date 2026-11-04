from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timezone

import discord

from utils.storage import carregar
from utils import monitoramento_membros
from utils.perfis import get_perfil
from utils import revisoes as revisoes_storage
from utils import punicoes as punicoes_storage
from utils.competitivo_sync import ARQUIVO_COMPETITIVO
from utils.apresentacao import criar_embed


log = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
ARQUIVO_PROGRESSAO = "progressao_gangue.json"
ARQUIVO_CONVITES = "convites_nemesis.json"
ARQUIVO_REGISTRO_GLOBAL = "registro_global_topicos.json"

# Categorias do Registro Global que podem conter ações ligadas a uma pessoa.
CATEGORIAS_HISTORICO = (
    "moderacao", "seguranca", "missoes", "competitivo",
    "atendimento", "parcerias", "sugestoes",
)

ABAS = (
    ("geral", "◈ Visão geral", "Identificação e indicadores essenciais do membro."),
    ("missoes", "🎯 Missões e atividades", "Provas, contribuições, aprovações e recusas."),
    ("competitivo", "⚔️ Competitivo", "XP, progressão, guerras e estatísticas de combate."),
    ("moderacao", "🛡️ Moderação", "Punições registradas e ocorrências de segurança."),
    ("mensagens", "💬 Mensagens", "Mensagens enviadas, editadas e excluídas nos últimos 30 dias."),
    ("atividade", "◷ Monitoramento", "Entradas, saídas, voz e alterações relevantes do membro."),
    ("registros", "📚 Linha do tempo", "Eventos relevantes registrados nos sistemas da NÊMESIS."),
)


def _inteiro(valor, padrao: int = 0) -> int:
    try:
        return max(0, int(valor or 0))
    except (TypeError, ValueError, OverflowError):
        return padrao


def _timestamp(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def filtrar_revisoes_membro(registros: list, user_id: int) -> list:
    """Inclui tanto o autor da prova quanto o auxiliar, sem duplicar protocolo."""
    uid = str(int(user_id))
    resultado = {}
    for item in registros if isinstance(registros, list) else []:
        if not isinstance(item, dict):
            continue
        if uid in {str(item.get("autor_id")), str(item.get("auxiliar_id"))}:
            chave = str(item.get("id") or id(item))
            resultado[chave] = item
    return sorted(
        resultado.values(),
        key=lambda item: _timestamp(
            item.get("aprovado_em") or item.get("rejeitada_em")
            or item.get("atualizado_em") or item.get("timestamp") or item.get("criado_em")
        ),
        reverse=True,
    )


def _resumo_revisoes(registros: list) -> dict:
    contagem = Counter(str(item.get("status") or "desconhecido") for item in registros)
    por_tipo = Counter(str(item.get("tipo") or "atividade") for item in registros)
    return {
        "total": len(registros),
        "aprovadas": contagem.get("aprovada", 0),
        "pendentes": contagem.get("pendente", 0),
        "rejeitadas": contagem.get("rejeitada", 0),
        "por_tipo": por_tipo,
    }


def _texto_seguro(valor, limite: int = 900, padrao: str = "Não registrado.") -> str:
    texto = str(valor or "").strip()
    return texto[:limite] if texto else padrao


def _data(timestamp: float) -> str:
    if not timestamp:
        return "Data não registrada"
    try:
        return discord.utils.format_dt(datetime.fromtimestamp(timestamp, tz=timezone.utc), style="R")
    except (ValueError, OverflowError, OSError):
        return "Data inválida"


async def _ler_documento(nome: str, padrao):
    try:
        dados = await carregar(nome, padrao)
        return dados if isinstance(dados, (dict, list)) else padrao
    except Exception:
        log.exception("Falha ao consultar %s para o dossiê individual.", nome)
        return padrao


async def _buscar_eventos_forum(guild: discord.Guild, user_id: int) -> list:
    """Consulta a trilha recente do Fórum privado, sem criar ou alterar tópicos."""
    ids = await _ler_documento(ARQUIVO_REGISTRO_GLOBAL, {})
    mapa = ids.get(str(guild.id), {}) if isinstance(ids, dict) else {}
    if not isinstance(mapa, dict):
        return []

    padrao_id = re.compile(rf"(?<!\d){int(user_id)}(?!\d)")
    mencao = re.compile(rf"<@!?{int(user_id)}>")
    semaforo = asyncio.Semaphore(4)

    async def ler_categoria(categoria: str):
        thread_id = mapa.get(categoria)
        if not thread_id:
            return []
        async with semaforo:
            try:
                canal = guild.get_thread(int(thread_id))
                if canal is None:
                    canal = await guild.fetch_channel(int(thread_id))
                if not isinstance(canal, discord.Thread) or canal.guild.id != guild.id:
                    return []
                encontrados = []
                async for mensagem in canal.history(limit=40, oldest_first=False):
                    partes = [mensagem.content or ""]
                    for embed in mensagem.embeds:
                        partes.extend((embed.title or "", embed.description or ""))
                        for campo in embed.fields:
                            partes.extend((campo.name or "", campo.value or ""))
                    texto = "\n".join(partes)
                    if padrao_id.search(texto) or mencao.search(texto):
                        titulo = next((e.title for e in mensagem.embeds if e.title), categoria.replace("_", " ").title())
                        descricao = next((e.description for e in mensagem.embeds if e.description), mensagem.content or "Registro sem descrição.")
                        encontrados.append({
                            "categoria": categoria,
                            "titulo": str(titulo)[:120],
                            "descricao": str(descricao)[:700],
                            "timestamp": mensagem.created_at.timestamp(),
                            "url": mensagem.jump_url,
                        })
                return encontrados
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                log.debug("Não foi possível consultar tópico de histórico %s.", categoria, exc_info=True)
                return []

    resultados = await asyncio.gather(*(ler_categoria(categoria) for categoria in CATEGORIAS_HISTORICO))
    eventos = [item for grupo in resultados for item in grupo]
    eventos.sort(key=lambda item: item["timestamp"], reverse=True)
    return eventos[:80]


async def construir_dossie(guild: discord.Guild, membro: discord.abc.User) -> dict:
    uid = int(membro.id)
    tarefas = await asyncio.gather(
        get_perfil(guild.id, uid),
        _ler_documento(ARQUIVO_PROGRESSAO, {}),
        revisoes_storage.listar(guild.id),
        punicoes_storage.historico_punicoes(guild.id, uid, limite=100),
        _ler_documento(ARQUIVO_CONVITES, {}),
        _ler_documento(ARQUIVO_COMPETITIVO, {"perfis": {}}),
        _buscar_eventos_forum(guild, uid),
        monitoramento_membros.consultar(guild.id, uid),
        return_exceptions=True,
    )

    def valor(indice, padrao):
        item = tarefas[indice]
        if isinstance(item, Exception):
            log.warning("Fonte %s indisponível no dossiê de %s: %s", indice, uid, item)
            return padrao
        return item

    perfil = valor(0, {})
    progressao_doc = valor(1, {})
    revisoes = valor(2, [])
    punicoes = valor(3, [])
    convites = valor(4, {})
    competitivo = valor(5, {"perfis": {}})
    eventos = valor(6, [])
    atividade = valor(7, {"mensagens": [], "eventos": []})

    progressao_guild = progressao_doc.get(str(guild.id), {}) if isinstance(progressao_doc, dict) else {}
    membros_progressao = progressao_guild.get("membros", {}) if isinstance(progressao_guild, dict) else {}
    progressao = membros_progressao.get(str(uid), {}) if isinstance(membros_progressao, dict) else {}

    revisoes_membro = filtrar_revisoes_membro(revisoes, uid)
    resumo_missoes = _resumo_revisoes(revisoes_membro)
    competitivo_perfis = competitivo.get("perfis", {}) if isinstance(competitivo, dict) else {}
    perfil_competitivo = competitivo_perfis.get(str(uid), {}) if isinstance(competitivo_perfis, dict) else {}

    servidor_convites = convites.get(str(guild.id), {}) if isinstance(convites, dict) else {}
    historico_convites = servidor_convites.get("_historico", {}) if isinstance(servidor_convites, dict) else {}
    convidador_id = historico_convites.get(str(uid)) if isinstance(historico_convites, dict) else None
    registro_convites = servidor_convites.get(str(uid), {}) if isinstance(servidor_convites, dict) else {}
    convidados_ativos = registro_convites.get("membros", []) if isinstance(registro_convites, dict) else []

    return {
        "guild": guild,
        "membro": membro,
        "perfil": perfil if isinstance(perfil, dict) else {},
        "progressao": progressao if isinstance(progressao, dict) else {},
        "perfil_competitivo": perfil_competitivo if isinstance(perfil_competitivo, dict) else {},
        "revisoes": revisoes_membro,
        "resumo_missoes": resumo_missoes,
        "punicoes": punicoes if isinstance(punicoes, list) else [],
        "convidador_id": convidador_id,
        "convidados_ativos": convidados_ativos if isinstance(convidados_ativos, list) else [],
        "eventos": eventos if isinstance(eventos, list) else [],
        "atividade": atividade if isinstance(atividade, dict) else {"mensagens": [], "eventos": []},
        "membro_presente": isinstance(membro, discord.Member),
    }


def _timeout_membro(membro):
    """Retorna o fim do timeout em diferentes versões de discord.py."""
    return getattr(membro, "timed_out_until", None) or getattr(membro, "communication_disabled_until", None)


def _embed_geral(d: dict) -> discord.Embed:
    membro = d["membro"]
    perfil = d["perfil"]
    progressao = d["progressao"]
    comp = d["perfil_competitivo"]
    resumo = d["resumo_missoes"]
    guild = d["guild"]
    presente = d["membro_presente"]

    embed = criar_embed(
        f"✦・ NÊMESIS — DOSSIÊ INDIVIDUAL ・✦",
        f"**{discord.utils.escape_markdown(membro.display_name if isinstance(membro, discord.Member) else membro.name)}**\n`{membro.id}` · {'🟢 Membro atual' if presente else '⚫ Não está mais no servidor'}",
        cor=0x9F2035,
        rodape="NÊMESIS • CENTRAL DE HISTÓRICO • ACESSO ADMINISTRATIVO",
    )
    embed.set_thumbnail(url=membro.display_avatar.url)

    criado = discord.utils.format_dt(membro.created_at, style="F")
    entrada = discord.utils.format_dt(membro.joined_at, style="F") if isinstance(membro, discord.Member) and membro.joined_at else "Não disponível"
    embed.add_field(name="◈ IDENTIDADE DISCORD", value=f"**Usuário:** `{membro.name}`\n**ID:** `{membro.id}`\n**Conta criada:** {criado}\n**Entrada no servidor:** {entrada}", inline=False)

    if isinstance(membro, discord.Member):
        estado = str(getattr(membro, "status", "indisponível")).replace("dnd", "Não perturbe").replace("online", "Online").replace("idle", "Ausente").replace("offline", "Offline")
        embed.add_field(name="◈ ESTADO", value=f"**Presença:** {estado}\n**Bot:** {'Sim' if membro.bot else 'Não'}\n**Timeout:** {discord.utils.format_dt(_timeout_membro(membro), style='R') if _timeout_membro(membro) else 'Não'}", inline=True)

    xp_org = _inteiro(progressao.get("xp"))
    rank_no = progressao.get("rank_no")
    ranks = (
        {12: "Lutador", 11: "Subtenente", 10: "Tenente", 9: "Executor", 8: "Especialista",
         7: "Elite", 6: "Veterano", 5: "Treinador", 4: "Comandante", 3: "Vice Capitão",
         2: "Capitão", 1: "Capitão Geral"}
    )
    rank_nome = ranks.get(_inteiro(rank_no, -1), "Não definido")
    embed.add_field(name="◈ PROGRESSÃO ORGANIZACIONAL", value=f"**Rank:** {rank_nome}\n**XP:** {xp_org:,}\n**Mensagens válidas:** {_inteiro(progressao.get('mensagens')):,}\n**Missões aprovadas:** {_inteiro(progressao.get('missoes'))}\n**Guerras registradas:** {_inteiro(progressao.get('guerras'))}".replace(",", "."), inline=True)
    embed.add_field(name="◈ ATIVIDADE COMPETITIVA", value=f"**Vitórias:** {_inteiro(perfil.get('vitorias'))}\n**Derrotas:** {_inteiro(perfil.get('derrotas'))}\n**Empates:** {_inteiro(perfil.get('empates'))}\n**Kills / Deaths:** {_inteiro(perfil.get('kills'))} / {_inteiro(perfil.get('deaths'))}\n**MVPs:** {_inteiro(perfil.get('mvps'))}", inline=True)
    embed.add_field(name="◈ PARTICIPAÇÃO NA NÊMESIS", value=f"**Provas vinculadas:** {resumo['total']}\n**Aprovadas:** {resumo['aprovadas']} · **Pendentes:** {resumo['pendentes']} · **Recusadas:** {resumo['rejeitadas']}\n**Punições registradas:** {len(d['punicoes'])}\n**Registros relevantes:** {len(d['eventos'])}", inline=False)
    embed.add_field(name="◈ RECRUTAMENTO", value=(f"**Convidado por:** <@{d['convidador_id']}>" if d["convidador_id"] else "**Convidador:** Não identificado") + f"\n**Convidados ativos atribuídos:** {len(d['convidados_ativos'])}", inline=True)
    embed.add_field(name="◈ REGISTRO DE DADOS", value="As informações são consolidadas dos sistemas e registros atualmente disponíveis. Um campo sem registro não significa que a ação nunca ocorreu.", inline=False)
    return embed


def _embed_missoes(d: dict) -> discord.Embed:
    resumo = d["resumo_missoes"]
    embed = criar_embed("🎯 NÊMESIS — MISSÕES E ATIVIDADES", "Histórico de provas em que o membro aparece como autor ou auxiliar.", cor=0x9F2035)
    embed.add_field(name="◈ INDICADORES", value=f"**Total:** {resumo['total']}\n**Aprovadas:** {resumo['aprovadas']}\n**Pendentes:** {resumo['pendentes']}\n**Rejeitadas:** {resumo['rejeitadas']}\n**Categorias:** {', '.join(f'{k}: {v}' for k, v in resumo['por_tipo'].items()) or 'Sem registros'}", inline=False)
    linhas = []
    for item in d["revisoes"][:12]:
        tipo = str(item.get("tipo") or "atividade").replace("_", " ").title()
        status = str(item.get("status") or "desconhecido").title()
        papel = "Autor" if str(item.get("autor_id")) == str(d['membro'].id) else "Auxiliar"
        titulo = discord.utils.escape_markdown(str(item.get("titulo") or item.get("referencia_id") or "Atividade")[:90])
        responsavel = f" · Revisor: <@{item.get('revisor_id')}>" if item.get("revisor_id") else ""
        motivo = f"\n↳ Motivo: {discord.utils.escape_markdown(str(item.get('motivo_rejeicao'))[:160])}" if item.get("motivo_rejeicao") else ""
        linhas.append(f"• **{titulo}** · {tipo} · **{status}**\n`{item.get('id', '—')}` · {papel}{responsavel}{motivo}")
    embed.add_field(name="◈ PROTOCOLOS RECENTES", value="\n\n".join(linhas)[:1024] if linhas else "Nenhuma prova vinculada encontrada.", inline=False)
    embed.set_footer(text="NÊMESIS • Dados obtidos dos protocolos oficiais de revisão")
    return embed


def _embed_competitivo(d: dict) -> discord.Embed:
    p = d["perfil"]
    prog = d["progressao"]
    comp = d["perfil_competitivo"]
    vitorias, derrotas, empates = _inteiro(p.get("vitorias")), _inteiro(p.get("derrotas")), _inteiro(p.get("empates"))
    kills, deaths = _inteiro(p.get("kills")), _inteiro(p.get("deaths"))
    kdr = round(kills / max(1, deaths), 2)
    embed = criar_embed("⚔️ NÊMESIS — DOSSIÊ COMPETITIVO", "Desempenho, progressão e marcos competitivos registrados.", cor=0x9F2035)
    embed.add_field(name="◈ COMBATE", value=f"**Vitórias:** {vitorias}\n**Derrotas:** {derrotas}\n**Empates:** {empates}\n**K/D:** {kills}/{deaths} · **KDR:** {kdr}\n**MVPs:** {_inteiro(p.get('mvps'))}\n**Sequência atual/máxima:** {_inteiro(p.get('sequencia_atual'))}/{_inteiro(p.get('maior_sequencia'))}", inline=True)
    embed.add_field(name="◈ ORGANIZAÇÃO", value=f"**XP:** {_inteiro(prog.get('xp')):,}\n**Rank nº:** {prog.get('rank_no', '—')}\n**Mensagens:** {_inteiro(prog.get('mensagens'))}\n**Missões aprovadas:** {_inteiro(prog.get('missoes'))}\n**Guerras registradas:** {_inteiro(prog.get('guerras'))}".replace(",", "."), inline=True)
    xp_comp = _inteiro(comp.get("xp", comp.get("xp_temporada")))
    embed.add_field(name="◈ RANKING COMPETITIVO", value=f"**XP competitivo:** {xp_comp:,}\n**Temporada:** {_inteiro(comp.get('xp_temporada')):,}\n**Medalhas:** {len(p.get('medalhas', []))}".replace(",", "."), inline=False)
    medalhas = p.get("medalhas", [])
    embed.add_field(name="◈ DISTINÇÕES DE COMBATE", value="\n".join(f"• {discord.utils.escape_markdown(str(x))[:100]}" for x in medalhas[:12]) if medalhas else "Nenhuma medalha registrada.", inline=False)
    return embed


def _embed_conquistas(d: dict) -> discord.Embed:
    desbloqueadas = d["conquistas"]
    temporadas = d["temporadas"]
    embed = criar_embed("🏅 NÊMESIS — CONQUISTAS E DISTINÇÕES", "Marcos individuais e resultados sazonais preservados.", cor=0x9F2035)
    from utils.conquistas import CATALOGO_POR_ID
    linhas = []
    for identificador, registro in sorted(desbloqueadas.items(), key=lambda item: _timestamp(item[1].get("desbloqueada_em")), reverse=True):
        meta = CATALOGO_POR_ID.get(identificador, {})
        linhas.append(f"• {meta.get('icone', '🏅')} **{meta.get('nome', identificador)}** · {meta.get('raridade', 'Conquista')} · {_data(_timestamp(registro.get('desbloqueada_em')))}")
    embed.add_field(name=f"◈ CONQUISTAS DESBLOQUEADAS ({len(linhas)})", value="\n".join(linhas[:15])[:1024] if linhas else "Nenhuma conquista desbloqueada registrada.", inline=False)
    sazonais = [f"• **Temporada #{_inteiro(x.get('temporada'))}** · {x.get('posicao', '—')}º lugar · {discord.utils.escape_markdown(str(x.get('recompensa') or 'Distinção sazonal'))[:100]}" for x in temporadas]
    embed.add_field(name=f"◈ DISTINÇÕES SAZONAIS ({len(sazonais)})", value="\n".join(sazonais[:12])[:1024] if sazonais else "Nenhuma colocação sazonal registrada.", inline=False)
    return embed


def _embed_moderacao(d: dict) -> discord.Embed:
    punicoes = d["punicoes"]
    eventos = [x for x in d["eventos"] if x["categoria"] in {"moderacao", "automod"}]
    embed = criar_embed("🛡️ NÊMESIS — HISTÓRICO DE MODERAÇÃO", "Registro administrativo de medidas e ocorrências vinculadas ao membro.", cor=0x9F2035)
    linhas = []
    for item in punicoes[:15]:
        tipo = str(item.get("tipo") or "Ação").upper()
        motivo = discord.utils.escape_markdown(str(item.get("motivo") or "Sem motivo")[:180])
        autor = f" · Responsável: <@{item.get('aplicado_por_id')}>" if item.get("aplicado_por_id") else ""
        linhas.append(f"• **{tipo}** · {_data(_timestamp(item.get('timestamp')))}\n↳ {motivo}{autor}")
    embed.add_field(name=f"◈ PUNIÇÕES REGISTRADAS ({len(punicoes)})", value="\n\n".join(linhas)[:1024] if linhas else "Nenhuma punição encontrada no banco de punições.", inline=False)
    recentes = [f"• **{x['titulo']}** · {x['categoria']} · {_data(x['timestamp'])}" for x in eventos[:10]]
    embed.add_field(name=f"◈ OCORRÊNCIAS AUTOMÁTICAS E ADMINISTRATIVAS ({len(eventos)})", value="\n".join(recentes)[:1024] if recentes else "Nenhuma ocorrência adicional localizada nos registros recentes.", inline=False)
    embed.set_footer(text="NÊMESIS • Consulta restrita à liderança autorizada")
    return embed


def _embed_mensagens(d: dict, pagina: int = 0) -> discord.Embed:
    mensagens = sorted(d.get("atividade", {}).get("mensagens", []), key=lambda x: _timestamp(x.get("timestamp")), reverse=True)
    por_pagina = 6
    total = len(mensagens)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(0, min(int(pagina), paginas - 1))
    inicio = pagina * por_pagina
    embed = criar_embed(
        "💬 NÊMESIS — HISTÓRICO DE MENSAGENS",
        f"Mensagens registradas nos últimos 30 dias (limite de 500) · {total} registro(s) · Página {pagina + 1}/{paginas}.",
        cor=0x9F2035,
    )
    for item in mensagens[inicio:inicio + por_pagina]:
        status = str(item.get("status", "enviada"))
        selo = {"excluida": "🗑️ EXCLUÍDA", "editada": "✏️ EDITADA"}.get(status, "🟢 ENVIADA")
        conteudo = discord.utils.escape_mentions(discord.utils.escape_markdown(str(item.get("conteudo") or "[mensagem sem texto]")[:650]))
        canal_id = item.get("canal_id")
        canal = f" <#{canal_id}>" if canal_id else " canal não identificado"
        data = _data(_timestamp(item.get("timestamp")))
        revisoes = item.get("revisoes", [])
        detalhe = ""
        if revisoes:
            anterior = str(revisoes[-1].get("conteudo", ""))[:220]
            anterior = discord.utils.escape_mentions(discord.utils.escape_markdown(anterior))
            detalhe = f"\n**Versão anterior:** {anterior or '[vazia]'}"
        if status == "excluida":
            detalhe += f"\n**Excluída em:** {_data(_timestamp(item.get('excluida_em')))}"
        anexos = item.get("anexos", [])
        if anexos:
            detalhe += "\n**Anexos:** " + ", ".join(str(a.get("nome", "arquivo"))[:60] for a in anexos[:4])
        valor = f"{conteudo}{detalhe}"
        if item.get("url"):
            valor += f"\n[Abrir mensagem no Discord]({item['url']})"
        embed.add_field(name=f"{selo} · {data}{canal}", value=valor[:1024], inline=False)
    if not mensagens:
        embed.description += "\n\nNenhuma mensagem foi capturada ainda. O monitoramento começa após a implantação; mensagens antigas não podem ser recuperadas pelo Discord."
    embed.set_footer(text="NÊMESIS • Até 500 mensagens / 30 dias • Consulta restrita à liderança")
    return embed


def _embed_atividade(d: dict) -> discord.Embed:
    eventos = sorted(d.get("atividade", {}).get("eventos", []), key=lambda x: _timestamp(x.get("timestamp")), reverse=True)
    embed = criar_embed("◷ NÊMESIS — MONITORAMENTO DE ATIVIDADE", f"Eventos individuais capturados nos últimos 30 dias · {len(eventos)} registro(s).", cor=0x9F2035)
    linhas = []
    for item in eventos[:18]:
        tipo = discord.utils.escape_markdown(str(item.get("tipo", "atividade")).replace("_", " ").title())
        descricao = discord.utils.escape_mentions(discord.utils.escape_markdown(str(item.get("descricao", ""))[:180]))
        linhas.append(f"• **{tipo}** · {_data(_timestamp(item.get('timestamp')))}\n↳ {descricao}")
    embed.add_field(name="◈ ATIVIDADES RECENTES", value="\n\n".join(linhas)[:4000] if linhas else "Nenhum evento de atividade foi capturado ainda.", inline=False)
    embed.add_field(name="◈ COBERTURA", value="Entradas e saídas; mudanças de presença e jogos; apelidos e identidade; cargos recebidos/removidos; impulsionamento; timeouts; entradas, saídas e estados de voz; banimentos e desbanimentos. Mensagens enviadas, editadas e excluídas ficam na aba própria. Captura iniciada após a implantação, com retenção de 30 dias e limites de armazenamento. Não inclui DMs, atividade fora do servidor nem histórico anterior à ativação.", inline=False)
    embed.set_footer(text="NÊMESIS • Retenção de 30 dias • Consulta restrita à liderança")
    return embed


def _embed_registros(d: dict) -> discord.Embed:
    eventos = d["eventos"]
    embed = criar_embed("📚 NÊMESIS — LINHA DO TEMPO INDIVIDUAL", "Eventos localizados nos tópicos privados do Registro Global.", cor=0x9F2035)
    linhas = []
    for item in eventos[:18]:
        titulo = discord.utils.escape_markdown(item["titulo"][:100])
        descricao = discord.utils.escape_markdown(item["descricao"].replace("\n", " ")[:120])
        linha = f"• **{titulo}** · `{item['categoria']}` · {_data(item['timestamp'])}\n↳ {descricao}"
        if item.get("url"):
            linha += f"\n[ Abrir registro ]({item['url']})"
        linhas.append(linha)
    if not linhas:
        embed.add_field(name="◈ EVENTOS LOCALIZADOS (0)", value="Nenhum evento recente foi localizado nos tópicos consultados.", inline=False)
    else:
        blocos, atual = [], ""
        for linha in linhas:
            candidato = f"{atual}\n\n{linha}" if atual else linha
            if len(candidato) > 950 and atual:
                blocos.append(atual)
                atual = linha
            else:
                atual = candidato
        if atual:
            blocos.append(atual)
        for indice, bloco in enumerate(blocos[:4], start=1):
            embed.add_field(name=f"◈ EVENTOS LOCALIZADOS · {indice}/{min(len(blocos), 4)}", value=bloco[:1024], inline=False)
    embed.add_field(name="◈ COBERTURA DA CONSULTA", value=f"Foram consultadas até 40 mensagens recentes em cada uma das {len(CATEGORIAS_HISTORICO)} categorias individuais configuradas. Os bancos de missões, punições e progressão são consultados separadamente e não dependem deste limite.", inline=False)
    embed.set_footer(text="NÊMESIS • Linha do tempo baseada nos registros efetivamente disponíveis")
    return embed



async def setup(bot):
    """Módulo de apoio; a interface é integrada ao Registro Global em cogs.logs."""
    return None
