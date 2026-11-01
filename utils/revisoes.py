import asyncio
import time
import uuid

from utils.storage import carregar, salvar


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


async def _tudo():
    dados = await carregar(ARQUIVO_REVISOES, {})
    return dados if isinstance(dados, dict) else {}


async def _salvar_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo()
    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_REVISOES,
        dados,
    )


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
    guild_id: int,
    tipo: str,
    autor_id: int,
    referencia_id: str,
    print_url: str,
    titulo: str,
    descricao: str = None,
    auxiliar_id: int = None,
    recompensa_xp: int = None,
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

        lista = await listar(guild_id)

        # Idempotência para provas PvP: duas chamadas quase simultâneas
        # não podem criar duas pendências para o mesmo desafio.
        if str(tipo).lower() == "pvp":
            existente = next(
                (
                    item for item in lista
                    if isinstance(item, dict)
                    and str(item.get("tipo", "")).lower() == "pvp"
                    and str(item.get("referencia_id")) == str(referencia_id)
                    and item.get("status") == "pendente"
                ),
                None,
            )
            if existente:
                return existente

        revisao = {
            "id": str(uuid.uuid4())[:8],
            "guild_id": guild_id,
            "tipo": tipo,
            "autor_id": autor_id,
            "referencia_id": referencia_id,
            "print_url": print_url,
            "titulo": titulo,
            "descricao": descricao,
            "auxiliar_id": int(auxiliar_id) if auxiliar_id else None,
            "recompensa_xp": max(0, int(recompensa_xp or 0)) if recompensa_xp is not None else None,
            "status": "pendente",
            "revisor_id": None,
            "motivo_rejeicao": None,
            "timestamp": time.time(),
            "mensagem_id": None,
            "canal_id": None,
            "hash_imagem": None,
            "criado_em": time.time(),
            "atualizado_em": time.time(),
            "trilha_auditoria": [],
        }
        _adicionar_evento_auditoria(revisao, "protocolo_criado", autor_id,
            status_anterior=None, status_novo="pendente", categoria=tipo,
            referencia_id=referencia_id)

        lista.append(revisao)

        await _salvar_guild(
            guild_id,
            lista,
        )

        return revisao


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
    guild_id: int,
    revisao_id: str,
    canal_id: int,
    mensagem_id: int,
):
    async with _REVISOES_LOCK:

        lista = await listar(guild_id)

        alvo = next(
            (
                revisao
                for revisao in lista
                if revisao.get("id") == revisao_id
            ),
            None,
        )

        if not alvo:
            return None

        alvo["canal_id"] = canal_id
        alvo["mensagem_id"] = mensagem_id
        alvo["atualizado_em"] = time.time()
        _adicionar_evento_auditoria(alvo, "mensagem_publicada",
            status_novo=alvo.get("status"), canal_id=canal_id, mensagem_id=mensagem_id)

        await _salvar_guild(
            guild_id,
            lista,
        )

        return alvo


async def definir_hash(
    guild_id: int,
    revisao_id: str,
    hash_imagem: str,
):
    async with _REVISOES_LOCK:

        lista = await listar(guild_id)

        alvo = next(
            (
                revisao
                for revisao in lista
                if revisao.get("id") == revisao_id
            ),
            None,
        )

        if not alvo:
            return None

        alvo["hash_imagem"] = hash_imagem
        alvo["atualizado_em"] = time.time()
        _adicionar_evento_auditoria(alvo, "hash_evidencia_registrado",
            status_novo=alvo.get("status"), hash_prefixo=str(hash_imagem)[:16])

        await _salvar_guild(
            guild_id,
            lista,
        )

        return alvo


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


async def aprovar(
    guild_id: int,
    revisao_id: str,
    revisor_id: int,
):
    async with _REVISOES_LOCK:

        lista = await listar(guild_id)

        alvo = next(
            (
                revisao
                for revisao in lista
                if revisao.get("id") == revisao_id
            ),
            None,
        )

        if not alvo:
            return None

        if alvo.get("status") != "pendente":
            return None

        status_anterior = alvo.get("status")
        alvo["status"] = "aprovada"
        alvo["revisor_id"] = revisor_id
        alvo["aprovado_em"] = time.time()
        alvo["atualizado_em"] = time.time()
        _adicionar_evento_auditoria(alvo, "protocolo_aprovado", revisor_id,
            status_anterior=status_anterior, status_novo="aprovada")

        await _salvar_guild(
            guild_id,
            lista,
        )

        return alvo


async def rejeitar(
    guild_id: int,
    revisao_id: str,
    revisor_id: int,
    motivo: str = None,
):
    motivo = str(motivo or "").strip()
    if len(motivo) < 8:
        raise ValueError("Informe um motivo de rejeição com pelo menos 8 caracteres.")
    motivo = motivo[:800]
    async with _REVISOES_LOCK:

        lista = await listar(guild_id)

        alvo = next(
            (
                revisao
                for revisao in lista
                if revisao.get("id") == revisao_id
            ),
            None,
        )

        if not alvo:
            return None

        if alvo.get("status") != "pendente":
            return None

        status_anterior = alvo.get("status")
        alvo["status"] = "rejeitada"
        alvo["revisor_id"] = revisor_id
        alvo["motivo_rejeicao"] = motivo
        alvo["rejeitada_em"] = time.time()
        alvo["atualizado_em"] = time.time()
        _adicionar_evento_auditoria(alvo, "protocolo_rejeitado", revisor_id,
            status_anterior=status_anterior, status_novo="rejeitada", justificativa=motivo)

        await _salvar_guild(
            guild_id,
            lista,
        )

        return alvo


async def reabrir_apos_falha_aplicacao(
    guild_id: int,
    revisao_id: str,
    erro_tipo: str = "Erro",
):
    """Devolve uma aprovação com falha para pendente, permitindo nova tentativa."""
    async with _REVISOES_LOCK:
        lista = await listar(guild_id)
        alvo = next(
            (item for item in lista if item.get("id") == revisao_id),
            None,
        )
        if not alvo or alvo.get("status") != "aprovada":
            return None

        status_anterior = alvo.get("status")
        alvo["status"] = "pendente"
        alvo["falha_aplicacao_tipo"] = str(erro_tipo)[:100]
        alvo["falha_aplicacao_em"] = time.time()
        alvo["atualizado_em"] = time.time()
        _adicionar_evento_auditoria(alvo, "aplicacao_reaberta_apos_falha",
            status_anterior=status_anterior, status_novo="pendente", erro_tipo=str(erro_tipo)[:100])
        await _salvar_guild(guild_id, lista)
        return alvo


async def normalizar_revisoes_guild(
    guild_id: int,
) -> int:
    async with _REVISOES_LOCK:

        lista = await listar(guild_id)

        quantidade = 0

        for revisao in lista:

            if not isinstance(revisao, dict):
                continue

            revisao.setdefault(
                "guild_id",
                guild_id,
            )

            revisao.setdefault(
                "atualizado_em",
                time.time(),
            )

            quantidade += 1

        await _salvar_guild(
            guild_id,
            lista,
        )

        return quantidade