import asyncio
import time
import uuid

from utils.storage import carregar, atualizar_json


ARQUIVO_REVISOES = "revisoes.json"
_REVISOES_LOCK = asyncio.Lock()



def _adicionar_evento_auditoria(revisao: dict, evento: str, ator_id: int = None, **detalhes) -> None:
    """Acrescenta evento à trilha sem alterar eventos anteriores."""
    trilha = revisao.get("trilha_auditoria")
    if not isinstance(trilha, list):
        trilha = []
        revisao["trilha_auditoria"] = trilha
    registro = {"evento": str(evento)[:60], "ator_id": int(ator_id) if ator_id else None, "em": time.time()}
    for chave, valor in detalhes.items():
        if valor is not None:
            registro[str(chave)[:60]] = str(valor)[:800] if isinstance(valor, str) else valor
    trilha.append(registro)


def analisar_integridade(revisoes: list, guild_id: int = None, agora: float = None) -> dict:
    """Inspeciona protocolos de missão sem alterar os dados persistidos."""
    agora = float(agora if agora is not None else time.time())
    tipos = {"missao", "contribuicao", "especial", "pve"}
    status_validos = {"pendente", "aprovada", "rejeitada"}
    ocorrencias = []
    registros_afetados = set()
    total, sem_trilha = 0, 0
    contagem_ids = {}
    for registro in revisoes:
        if isinstance(registro, dict) and str(registro.get("tipo") or "").lower() in tipos:
            codigo = str(registro.get("id") or "").strip()
            if codigo:
                contagem_ids[codigo] = contagem_ids.get(codigo, 0) + 1

    def apontar(item, codigo, nivel, descricao):
        registros_afetados.add(id(item))
        ocorrencias.append({
            "protocolo": str(item.get("id") or "SEM-ID"),
            "titulo": str(item.get("titulo") or "Protocolo sem título")[:100],
            "codigo": codigo, "severidade": nivel, "descricao": descricao,
            "tipo": str(item.get("tipo") or "—"), "autor_id": item.get("autor_id"),
        })

    for item in revisoes:
        if not isinstance(item, dict) or str(item.get("tipo") or "").lower() not in tipos:
            continue
        total += 1
        protocolo = str(item.get("id") or "").strip()
        if not protocolo:
            apontar(item, "id_ausente", "critica", "Protocolo sem identificador.")
        elif contagem_ids.get(protocolo, 0) > 1:
            apontar(item, "id_duplicado", "critica", "Identificador repetido em outro protocolo.")
        if item.get("status") not in status_validos:
            apontar(item, "status_invalido", "critica", "Situação ausente ou não reconhecida.")
        if guild_id is not None and item.get("guild_id") is not None:
            try:
                if int(item["guild_id"]) != int(guild_id):
                    apontar(item, "servidor_divergente", "critica", "Servidor registrado não corresponde ao analisado.")
            except (TypeError, ValueError, OverflowError):
                apontar(item, "servidor_invalido", "alta", "Identificador de servidor inválido.")
        recompensa = item.get("recompensa_xp")
        if recompensa is not None:
            try:
                numero = int(recompensa)
                if numero < 0 or str(numero) != str(recompensa).strip():
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                apontar(item, "recompensa_invalida", "alta", "Recompensa XP não é um inteiro não negativo.")

        datas = {}
        for chave in ("timestamp", "criado_em", "aprovado_em", "rejeitada_em", "atualizado_em"):
            valor = item.get(chave)
            if valor is None:
                datas[chave] = None
                continue
            try:
                numero = float(valor)
                if numero <= 0 or numero > agora + 300:
                    raise ValueError
                datas[chave] = numero
            except (TypeError, ValueError, OverflowError):
                datas[chave] = None
                apontar(item, "data_" + chave + "_invalida", "media", "Campo de data inválido: " + chave + ".")
        if datas["timestamp"] and datas["criado_em"] and datas["criado_em"] + 300 < datas["timestamp"]:
            apontar(item, "ordem_criacao_invalida", "media", "Criação antecede o envio da evidência.")
        decisao = datas["aprovado_em"] if item.get("status") == "aprovada" else datas["rejeitada_em"]
        if decisao and datas["atualizado_em"] and datas["atualizado_em"] + 300 < decisao:
            apontar(item, "ordem_decisao_invalida", "media", "Atualização antecede a decisão.")
        if item.get("status") == "aprovada":
            if not datas["aprovado_em"]:
                apontar(item, "aprovacao_sem_data", "alta", "Aprovação sem data válida.")
            if not item.get("revisor_id"):
                apontar(item, "aprovacao_sem_revisor", "alta", "Aprovação sem responsável.")
        elif item.get("status") == "rejeitada":
            if not datas["rejeitada_em"]:
                apontar(item, "rejeicao_sem_data", "alta", "Rejeição sem data válida.")
            if not item.get("revisor_id"):
                apontar(item, "rejeicao_sem_revisor", "alta", "Rejeição sem responsável.")
            if len(str(item.get("motivo_rejeicao") or "").strip()) < 8:
                apontar(item, "rejeicao_sem_motivo", "alta", "Rejeição sem justificativa suficiente.")
        elif item.get("status") == "pendente" and (datas["aprovado_em"] or datas["rejeitada_em"] or item.get("revisor_id")):
            apontar(item, "pendencia_com_decisao", "alta", "Pendência contém metadados de decisão.")

        trilha = item.get("trilha_auditoria")
        if not isinstance(trilha, list) or not trilha:
            sem_trilha += 1
            continue
        ultimo_status, ultimo_tempo = None, None
        for evento in trilha:
            if not isinstance(evento, dict) or not evento.get("evento"):
                apontar(item, "evento_auditoria_invalido", "alta", "Evento sem estrutura válida na trilha.")
                continue
            try:
                instante = float(evento.get("em"))
                if instante <= 0 or instante > agora + 300:
                    raise ValueError
                if ultimo_tempo is not None and instante < ultimo_tempo:
                    apontar(item, "ordem_trilha_invalida", "media", "Eventos fora da ordem cronológica.")
                ultimo_tempo = instante
            except (TypeError, ValueError, OverflowError):
                apontar(item, "data_evento_invalida", "media", "Evento com data inválida.")
            if evento.get("status_novo"):
                ultimo_status = evento["status_novo"]
        if ultimo_status and ultimo_status != item.get("status"):
            apontar(item, "trilha_divergente", "critica", "Último status da trilha difere do status atual.")

    niveis = ("critica", "alta", "media")
    contagens = {nivel: sum(1 for o in ocorrencias if o["severidade"] == nivel) for nivel in niveis}
    return {
        "protocolos_analisados": total, "ocorrencias": ocorrencias,
        "total_ocorrencias": len(ocorrencias), "criticas": contagens["critica"],
        "altas": contagens["alta"], "medias": contagens["media"],
        "sem_trilha": sem_trilha,
        "integridade_percentual": round(max(0, (total - len(registros_afetados)) / total * 100), 1) if total else 100.0,
    }


def analisar_qualidade(revisoes: list, agora: float = None, janela_dias: int = 30) -> dict:
    """Gera indicadores de qualidade sem classificar automaticamente uma prova como fraude."""
    from collections import defaultdict
    from math import isfinite
    from statistics import median

    agora = float(agora if agora is not None else time.time())
    janela_dias = max(1, min(int(janela_dias), 3650))
    tipos = {"missao", "contribuicao", "especial", "pve"}
    validas = [r for r in revisoes if isinstance(r, dict) and str(r.get("tipo") or "").lower() in tipos]
    limite = agora - janela_dias * 86400
    recentes = []
    for item in validas:
        envio = None
        for campo in ("timestamp", "criado_em"):
            try:
                valor = item.get(campo)
                if valor is not None:
                    candidato = float(valor)
                    if isfinite(candidato) and candidato > 0:
                        envio = candidato
                        break
            except (TypeError, ValueError, OverflowError):
                continue
        if envio is not None and envio <= agora + 300 and envio >= limite:
            recentes.append((item, envio))

    hashes = defaultdict(list)
    for item in validas:
        digest = str(item.get("hash_imagem") or "").strip().lower()
        if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            hashes[digest].append(item)
    duplicadas = []
    for digest, grupo in hashes.items():
        if len(grupo) < 2:
            continue
        autores = {str(x.get("autor_id") or "") for x in grupo}
        duplicadas.append({
            "hash_prefixo": digest[:12], "protocolos": [str(x.get("id") or "—") for x in grupo[:8]],
            "participantes": sorted(x for x in autores if x), "quantidade": len(grupo),
            "entre_participantes": len(autores - {""}) > 1,
        })

    por_autor = defaultdict(list)
    for item, envio in recentes:
        autor = str(item.get("autor_id") or "")
        if autor:
            por_autor[autor].append(envio)
    padroes = []
    for autor, momentos in por_autor.items():
        momentos.sort()
        maior = inicio = 0
        for fim in range(len(momentos)):
            while momentos[fim] - momentos[inicio] > 600:
                inicio += 1
            maior = max(maior, fim - inicio + 1)
        if maior >= 3:
            padroes.append({"autor_id": autor, "envios_10min": maior, "descricao": "Três ou mais evidências enviadas em uma janela de 10 minutos."})
    padroes.sort(key=lambda x: (-x["envios_10min"], x["autor_id"]))

    por_revisor = defaultdict(lambda: {"decisoes": 0, "aprovadas": 0, "rejeitadas": 0, "tempos_min": []})
    for item, envio in recentes:
        if item.get("status") not in {"aprovada", "rejeitada"} or not item.get("revisor_id"):
            continue
        revisor = str(item["revisor_id"]); dados = por_revisor[revisor]
        decisao_chave = "aprovado_em" if item["status"] == "aprovada" else "rejeitada_em"
        try:
            decisao = float(item.get(decisao_chave))
            if not isfinite(decisao) or decisao <= 0 or decisao > agora + 300 or decisao < envio:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        dados["decisoes"] += 1
        dados["aprovadas" if item["status"] == "aprovada" else "rejeitadas"] += 1
        dados["tempos_min"].append((decisao - envio) / 60)
    revisores = []
    for uid, dados in por_revisor.items():
        tempos = dados.pop("tempos_min")
        dados["mediana_minutos"] = round(median(tempos), 1) if tempos else None
        dados["taxa_rejeicao"] = round(dados["rejeitadas"] / dados["decisoes"] * 100, 1) if dados["decisoes"] else 0
        dados["alerta_amostra"] = dados["decisoes"] >= 5 and dados["taxa_rejeicao"] >= 80
        dados["revisor_id"] = uid
        revisores.append(dados)
    revisores.sort(key=lambda x: (-x["decisoes"], x["revisor_id"]))
    return {"janela_dias": janela_dias, "evidencias_analisadas": len(recentes),
            "duplicidades": duplicadas, "padroes_envio": padroes, "revisores": revisores,
            "decisoes_com_tempo": sum(x["decisoes"] for x in revisores)}


async def _tudo():
    dados = await carregar(ARQUIVO_REVISOES, {})
    return dados if isinstance(dados, dict) else {}


async def _atualizar_guild(guild_id: int, transformador):
    """Aplica mutações sobre a versão mais recente do documento via CAS."""
    chave = str(guild_id)

    def aplicar(documento):
        if not isinstance(documento, dict):
            documento = {}
        lista = documento.get(chave, [])
        if not isinstance(lista, list):
            lista = []
        lista = [item for item in lista if isinstance(item, dict)]
        transformador(lista)
        documento[chave] = lista
        return documento

    documento = await atualizar_json(ARQUIVO_REVISOES, {}, aplicar)
    lista = documento.get(chave, [])
    return lista if isinstance(lista, list) else []


async def listar(
    guild_id: int,
    status: str = None,
) -> list:

    dados = await _tudo()

    lista = dados.get(str(guild_id), [])
    if not isinstance(lista, list):
        return []

    # Ignora entradas legadas inválidas para que uma única linha corrompida
    # não impeça a staff de revisar as demais provas.
    lista = [revisao for revisao in lista if isinstance(revisao, dict)]
    if status:
        lista = [revisao for revisao in lista if revisao.get("status") == status]
    return lista


async def criar_pendencia(
    guild_id: int, tipo: str, autor_id: int, referencia_id: str,
    print_url: str, titulo: str, descricao: str = None,
    auxiliar_id: int = None, recompensa_xp: int = None,
) -> dict:
    tipo = str(tipo or "").strip().lower()
    if tipo not in {"pvp", "pve", "missao", "contribuicao", "especial"}:
        raise ValueError("Tipo de revisão inválido.")
    if not str(referencia_id or "").strip():
        raise ValueError("A revisão precisa de uma referência válida.")
    if not str(print_url or "").strip():
        raise ValueError("A revisão precisa de uma evidência válida.")
    if not str(titulo or "").strip():
        raise ValueError("A revisão precisa de um título.")
    if auxiliar_id and int(auxiliar_id) == int(autor_id):
        raise ValueError("O participante não pode ser o próprio auxiliar.")

    async with _REVISOES_LOCK:
        revisao = {
            "id": str(uuid.uuid4())[:8], "guild_id": guild_id,
            "tipo": tipo, "autor_id": autor_id, "referencia_id": referencia_id,
            "print_url": print_url, "titulo": titulo, "descricao": descricao,
            "auxiliar_id": int(auxiliar_id) if auxiliar_id else None,
            "recompensa_xp": max(0, int(recompensa_xp or 0)) if recompensa_xp is not None else None,
            "status": "pendente", "revisor_id": None, "motivo_rejeicao": None,
            "timestamp": time.time(), "mensagem_id": None, "canal_id": None,
            "hash_imagem": None, "criado_em": time.time(),
            "atualizado_em": time.time(), "trilha_auditoria": [],
        }
        _adicionar_evento_auditoria(
            revisao, "protocolo_criado", autor_id,
            status_anterior=None, status_novo="pendente",
            categoria=tipo, referencia_id=referencia_id,
        )
        resultado = {"revisao": None}

        def aplicar(lista):
            if tipo in {"pvp", "pve", "missao", "contribuicao", "especial"}:
                existente = next((
                    item for item in lista
                    if str(item.get("tipo", "")).lower() == tipo
                    and str(item.get("referencia_id")) == str(referencia_id)
                    and item.get("status") == "pendente"
                    and (
                        tipo == "pvp"
                        or str(item.get("autor_id")) == str(autor_id)
                    )
                ), None)
                if existente:
                    resultado["revisao"] = existente
                    return
            lista.append(revisao)
            resultado["revisao"] = revisao

        await _atualizar_guild(guild_id, aplicar)
        return resultado["revisao"]

async def get(
    guild_id: int,
    revisao_id: str,
):
    lista = await listar(guild_id)

    return next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )


async def definir_mensagem(
    guild_id: int, revisao_id: str, canal_id: int, mensagem_id: int,
):
    async with _REVISOES_LOCK:
        resultado = {"alvo": None}
        def aplicar(lista):
            alvo = next((item for item in lista if item.get("id") == revisao_id), None)
            if not alvo:
                resultado["alvo"] = None
                return
            alvo["canal_id"], alvo["mensagem_id"] = canal_id, mensagem_id
            alvo["atualizado_em"] = time.time()
            _adicionar_evento_auditoria(
                alvo, "mensagem_publicada", status_novo=alvo.get("status"),
                canal_id=canal_id, mensagem_id=mensagem_id,
            )
            resultado["alvo"] = alvo
        await _atualizar_guild(guild_id, aplicar)
        return resultado["alvo"]

async def definir_hash(guild_id: int, revisao_id: str, hash_imagem: str):
    async with _REVISOES_LOCK:
        resultado = {"alvo": None}
        def aplicar(lista):
            alvo = next((item for item in lista if item.get("id") == revisao_id), None)
            if not alvo:
                resultado["alvo"] = None
                return
            alvo["hash_imagem"] = hash_imagem
            alvo["atualizado_em"] = time.time()
            _adicionar_evento_auditoria(
                alvo, "hash_evidencia_registrado",
                status_novo=alvo.get("status"), hash_prefixo=str(hash_imagem)[:16],
            )
            resultado["alvo"] = alvo
        await _atualizar_guild(guild_id, aplicar)
        return resultado["alvo"]

async def buscar_por_hash(
    guild_id: int,
    hash_imagem: str,
    excluir_id: str = None,
) -> list:

    lista = await listar(guild_id)

    return [
        revisao
        for revisao in lista
        if (
            revisao.get("hash_imagem")
            == hash_imagem
            and revisao.get("id") != excluir_id
            and revisao.get("status") != "rejeitada"
        )
    ]


async def aprovar(guild_id: int, revisao_id: str, revisor_id: int):
    async with _REVISOES_LOCK:
        resultado = {"alvo": None}

        def aplicar(lista):
            alvo = next((item for item in lista if item.get("id") == revisao_id), None)
            if not alvo or alvo.get("status") != "pendente":
                resultado["alvo"] = None
                return
            agora = time.time()
            alvo["status"] = "aprovada"
            alvo["revisor_id"] = revisor_id
            alvo["aprovado_em"] = agora
            alvo["atualizado_em"] = agora
            _adicionar_evento_auditoria(
                alvo, "protocolo_aprovado", revisor_id,
                status_anterior="pendente", status_novo="aprovada",
            )
            resultado["alvo"] = alvo

        await _atualizar_guild(guild_id, aplicar)
        return resultado["alvo"]

async def rejeitar(
    guild_id: int, revisao_id: str, revisor_id: int, motivo: str = None,
):
    motivo = str(motivo or "").strip()
    if len(motivo) < 8:
        raise ValueError("Informe um motivo de rejeição com pelo menos 8 caracteres.")
    motivo = motivo[:800]
    async with _REVISOES_LOCK:
        resultado = {"alvo": None}

        def aplicar(lista):
            alvo = next((item for item in lista if item.get("id") == revisao_id), None)
            if not alvo or alvo.get("status") != "pendente":
                resultado["alvo"] = None
                return
            agora = time.time()
            alvo["status"] = "rejeitada"
            alvo["revisor_id"] = revisor_id
            alvo["motivo_rejeicao"] = motivo
            alvo["rejeitada_em"] = agora
            alvo["atualizado_em"] = agora
            _adicionar_evento_auditoria(
                alvo, "protocolo_rejeitado", revisor_id,
                status_anterior="pendente", status_novo="rejeitada",
                justificativa=motivo,
            )
            resultado["alvo"] = alvo

        await _atualizar_guild(guild_id, aplicar)
        return resultado["alvo"]

async def reabrir_apos_falha_aplicacao(
    guild_id: int, revisao_id: str, erro_tipo: str = "Erro",
):
    """Devolve uma aprovação com falha para pendente sem sobrescrever dados concorrentes."""
    async with _REVISOES_LOCK:
        resultado = {"alvo": None}

        def aplicar(lista):
            alvo = next((item for item in lista if item.get("id") == revisao_id), None)
            if not alvo or alvo.get("status") != "aprovada":
                resultado["alvo"] = None
                return
            agora = time.time()
            alvo["status"] = "pendente"
            alvo["falha_aplicacao_tipo"] = str(erro_tipo)[:100]
            alvo["falha_aplicacao_em"] = agora
            alvo["atualizado_em"] = agora
            _adicionar_evento_auditoria(
                alvo, "aplicacao_reaberta_apos_falha",
                status_anterior="aprovada", status_novo="pendente",
                erro_tipo=str(erro_tipo)[:100],
            )
            resultado["alvo"] = alvo

        await _atualizar_guild(guild_id, aplicar)
        return resultado["alvo"]

async def normalizar_revisoes_guild(guild_id: int) -> int:
    async with _REVISOES_LOCK:
        resultado = {"quantidade": 0}

        def aplicar(lista):
            for revisao in lista:
                revisao.setdefault("guild_id", guild_id)
                revisao.setdefault("atualizado_em", time.time())
            resultado["quantidade"] = len(lista)

        await _atualizar_guild(guild_id, aplicar)
        return resultado["quantidade"]