"""Temporadas independentes para o sistema de missões da NÊMESIS.

A pontuação sazonal é derivada exclusivamente das revisões oficiais aprovadas.
Este módulo não altera perfis, XP permanente, patentes, cargos ou ranking global.
"""
import asyncio
import math
import time

from utils.storage import carregar, atualizar_json
from utils import revisoes


ARQUIVO_TEMPORADAS_MISSOES = "temporadas_missoes.json"
_LOCK = asyncio.Lock()
TIPOS_MISSOES = {"missao", "contribuicao", "especial", "pve"}

ESTADO_PADRAO = {
    "numero_atual": 1,
    "inicio_timestamp": None,
    "fim_timestamp": None,
    "duracao_dias": 30,
    "meta_xp": 10000,
    "canal_id": None,
    "recompensas": {
        "1": "Distinção de Campeão da Temporada",
        "2": "Distinção de Vice-Campeão",
        "3": "Distinção de Destaque",
    },
    "historico": [],
    "anuncios_pendentes": [],
}


def _inteiro(valor, padrao=0, minimo=0, maximo=None):
    try:
        numero = int(valor)
    except (TypeError, ValueError, OverflowError):
        numero = int(padrao)
    numero = max(minimo, numero)
    if maximo is not None:
        numero = min(maximo, numero)
    return numero


def _normalizar_estado(estado):
    base = {
        **ESTADO_PADRAO,
        "recompensas": dict(ESTADO_PADRAO["recompensas"]),
        "historico": [],
        "anuncios_pendentes": [],
    }
    if isinstance(estado, dict):
        base.update(estado)
    base["numero_atual"] = _inteiro(base.get("numero_atual"), 1, 1)
    base["duracao_dias"] = _inteiro(base.get("duracao_dias"), 30, 1, 365)
    base["meta_xp"] = _inteiro(base.get("meta_xp"), 10000, 1, 100_000_000)
    for campo in ("inicio_timestamp", "fim_timestamp"):
        try:
            valor = float(base[campo]) if base.get(campo) is not None else None
            if valor is not None and (not math.isfinite(valor) or valor <= 0):
                valor = None
        except (TypeError, ValueError, OverflowError):
            valor = None
        base[campo] = valor
    try:
        base["canal_id"] = int(base["canal_id"]) if base.get("canal_id") else None
    except (TypeError, ValueError, OverflowError):
        base["canal_id"] = None
    if not isinstance(base.get("recompensas"), dict):
        base["recompensas"] = dict(ESTADO_PADRAO["recompensas"])
    else:
        base["recompensas"] = {
            str(pos): str(base["recompensas"].get(str(pos)) or "").strip()[:100]
            for pos in (1, 2, 3)
        }
    if not isinstance(base.get("historico"), list):
        base["historico"] = []
    if not isinstance(base.get("anuncios_pendentes"), list):
        base["anuncios_pendentes"] = []
    return base


async def _todos():
    dados = await carregar(ARQUIVO_TEMPORADAS_MISSOES, {})
    return dados if isinstance(dados, dict) else {}


async def get_estado(guild_id: int) -> dict:
    dados = await _todos()
    return _normalizar_estado(dados.get(str(guild_id), {}))


async def _atualizar_estado(guild_id: int, transformador):
    chave = str(guild_id)

    def aplicar(documento):
        if not isinstance(documento, dict):
            documento = {}
        estado = _normalizar_estado(documento.get(chave, {}))
        novo_estado = transformador(estado)
        documento[chave] = novo_estado if isinstance(novo_estado, dict) else estado
        return documento

    dados = await atualizar_json(ARQUIVO_TEMPORADAS_MISSOES, {}, aplicar)
    return _normalizar_estado(dados.get(chave, {}))


async def configurar(guild_id: int, agora: float = None, **campos) -> dict:
    agora = float(agora if agora is not None else time.time())
    if not math.isfinite(agora) or agora <= 0:
        raise ValueError("O horário informado é inválido.")

    if campos.get("duracao_dias") is not None:
        try:
            duracao = int(campos["duracao_dias"])
        except (TypeError, ValueError, OverflowError) as erro:
            raise ValueError("A duração precisa ser um número inteiro.") from erro
        if duracao < 1 or duracao > 365:
            raise ValueError("A duração deve ficar entre 1 e 365 dias.")
        campos["duracao_dias"] = duracao
    if campos.get("meta_xp") is not None:
        try:
            meta = int(campos["meta_xp"])
        except (TypeError, ValueError, OverflowError) as erro:
            raise ValueError("A meta coletiva precisa ser um número inteiro.") from erro
        if meta < 1 or meta > 100_000_000:
            raise ValueError("A meta coletiva deve ficar entre 1 e 100.000.000 XP.")
        campos["meta_xp"] = meta
    if campos.get("canal_id") is not None:
        campos["canal_id"] = int(campos["canal_id"])
    for pos in (1, 2, 3):
        chave = f"recompensa_{pos}"
        if campos.get(chave) is not None:
            campos[chave] = str(campos[chave]).strip()[:100]
            if not campos[chave]:
                raise ValueError("As descrições das recompensas não podem ficar vazias.")

    async with _LOCK:
        def aplicar(estado):
            recompensas = dict(estado["recompensas"])
            for chave, valor in campos.items():
                if chave.startswith("recompensa_"):
                    recompensas[chave.rsplit("_", 1)[1]] = valor
                elif valor is not None:
                    estado[chave] = valor
            estado["recompensas"] = recompensas

            if estado["inicio_timestamp"] is None:
                estado["inicio_timestamp"] = agora
                estado["fim_timestamp"] = agora + estado["duracao_dias"] * 86400
            elif campos.get("duracao_dias") is not None:
                estado["fim_timestamp"] = (
                    estado["inicio_timestamp"] + estado["duracao_dias"] * 86400
                )
            return estado

        return await _atualizar_estado(guild_id, aplicar)


def _timestamp_aprovacao(registro: dict):
    try:
        valor = float(registro.get("aprovado_em"))
        if math.isfinite(valor) and valor > 0:
            return valor
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _distribuir_xp(registro: dict):
    try:
        total = max(0, int(registro.get("recompensa_xp")))
    except (TypeError, ValueError, OverflowError):
        return []
    try:
        autor = int(registro.get("autor_id") or 0)
    except (TypeError, ValueError, OverflowError):
        return []
    if autor <= 0:
        return []
    try:
        auxiliar = int(registro.get("auxiliar_id") or 0)
    except (TypeError, ValueError, OverflowError):
        auxiliar = 0
    if auxiliar <= 0 or auxiliar == autor:
        return [(str(autor), total)]
    parte_autor = (total * 60 + 50) // 100
    return [(str(autor), parte_autor), (str(auxiliar), total - parte_autor)]


async def calcular_resultados(
    guild_id: int,
    inicio_timestamp: float,
    fim_timestamp: float,
    agora: float = None,
) -> dict:
    """Calcula ranking e meta sem escrever em qualquer perfil ou histórico de XP."""
    agora = float(agora if agora is not None else time.time())
    inicio = float(inicio_timestamp)
    fim = min(float(fim_timestamp), agora)
    registros = await revisoes.listar(guild_id)
    pontuacao = {}
    protocolos = set()
    xp_coletivo = 0
    aprovadas = 0

    for registro in registros:
        if not isinstance(registro, dict):
            continue
        if str(registro.get("tipo") or "").lower() not in TIPOS_MISSOES:
            continue
        if registro.get("status") != "aprovada":
            continue
        momento = _timestamp_aprovacao(registro)
        if momento is None or momento < inicio or momento > fim:
            continue
        protocolo = str(registro.get("id") or "").strip()
        if not protocolo or protocolo in protocolos:
            continue
        distribuicao = _distribuir_xp(registro)
        if not distribuicao:
            continue
        protocolos.add(protocolo)
        aprovadas += 1
        for uid, quantidade in distribuicao:
            pontuacao[uid] = pontuacao.get(uid, 0) + quantidade
            xp_coletivo += quantidade

    ranking = sorted(
        pontuacao.items(),
        key=lambda item: (-item[1], int(item[0])),
    )
    return {
        "ranking": [
            {"user_id": int(uid), "xp": xp, "posicao": pos}
            for pos, (uid, xp) in enumerate(ranking, 1)
        ],
        "xp_coletivo": xp_coletivo,
        "provas_aprovadas": aprovadas,
        "participantes": len(pontuacao),
    }


async def obter_status(guild_id: int, agora: float = None) -> dict:
    agora = float(agora if agora is not None else time.time())
    estado = await get_estado(guild_id)
    if estado["inicio_timestamp"] is None or estado["fim_timestamp"] is None:
        return {"configurada": False, "estado": estado}
    resultados = await calcular_resultados(
        guild_id, estado["inicio_timestamp"], estado["fim_timestamp"], agora
    )
    restante = max(0, estado["fim_timestamp"] - agora)
    meta = estado["meta_xp"]
    resultados.update({
        "configurada": True,
        "estado": estado,
        "restante_segundos": restante,
        "meta_xp": meta,
        "meta_atingida": resultados["xp_coletivo"] >= meta,
        "progresso_percentual": min(100, round(resultados["xp_coletivo"] / meta * 100, 1)),
    })
    return resultados


async def encerrar_temporada(guild_id: int, agora: float = None) -> dict:
    """Arquiva os resultados e abre a próxima temporada sem tocar no XP permanente."""
    agora = float(agora if agora is not None else time.time())
    if not math.isfinite(agora) or agora <= 0:
        raise ValueError("O horário de encerramento é inválido.")

    async with _LOCK:
        estado = await get_estado(guild_id)
        inicio = estado.get("inicio_timestamp")
        fim = estado.get("fim_timestamp")
        if inicio is None or fim is None:
            raise ValueError("Nenhuma temporada de missões está ativa.")
        if agora < inicio:
            raise ValueError("O horário de encerramento antecede o início da temporada.")

        numero = estado["numero_atual"]
        if any(
            isinstance(item, dict) and _inteiro(item.get("numero"), -1, 0) == numero
            for item in estado["historico"]
        ):
            raise ValueError("Esta temporada já foi encerrada.")

        resultados = await calcular_resultados(guild_id, inicio, min(fim, agora), agora)
        registro = {
            "numero": numero,
            "inicio_timestamp": inicio,
            "fim_timestamp": min(fim, agora),
            "encerrada_em": agora,
            "duracao_dias": round((min(fim, agora) - inicio) / 86400, 2),
            "meta_xp": estado["meta_xp"],
            "xp_coletivo": resultados["xp_coletivo"],
            "meta_atingida": resultados["xp_coletivo"] >= estado["meta_xp"],
            "provas_aprovadas": resultados["provas_aprovadas"],
            "participantes": resultados["participantes"],
            # O arquivo conserva o Top 10; os reconhecimentos são destinados
            # às três primeiras posições e o ranking completo permanece
            # recalculável a partir do histórico oficial de revisões.
            "ranking": resultados["ranking"][:10],
            "recompensas": dict(estado["recompensas"]),
            "canal_id": estado.get("canal_id"),
        }
        def aplicar(estado_atual):
            # Impede que um resultado calculado sobre uma temporada antiga
            # sobrescreva uma configuração ou encerramento concorrente.
            if (
                estado_atual.get("numero_atual") != numero
                or estado_atual.get("inicio_timestamp") != inicio
                or estado_atual.get("fim_timestamp") != fim
            ):
                raise ValueError("A temporada foi alterada durante o encerramento; atualize o painel e tente novamente.")
            if any(
                isinstance(item, dict)
                and _inteiro(item.get("numero"), -1, 0) == numero
                for item in estado_atual["historico"]
            ):
                raise ValueError("Esta temporada já foi encerrada.")

            estado_atual["historico"] = (list(estado_atual["historico"]) + [registro])[-100:]
            estado_atual["anuncios_pendentes"] = (
                list(estado_atual["anuncios_pendentes"]) + [registro]
            )[-20:]
            estado_atual["numero_atual"] = numero + 1
            estado_atual["inicio_timestamp"] = agora
            estado_atual["fim_timestamp"] = agora + estado_atual["duracao_dias"] * 86400
            return estado_atual

        await _atualizar_estado(guild_id, aplicar)
        return registro


async def listar_historico(guild_id: int, limite: int = 5) -> list:
    estado = await get_estado(guild_id)
    return list(reversed(estado["historico"][-max(1, min(int(limite), 20)):]))


async def listar_anuncios_pendentes(guild_id: int) -> list:
    estado = await get_estado(guild_id)
    return list(estado["anuncios_pendentes"])


async def marcar_anuncio_enviado(guild_id: int, numero: int):
    async with _LOCK:
        def aplicar(estado):
            estado["anuncios_pendentes"] = [
                item for item in estado["anuncios_pendentes"]
                if not (
                    isinstance(item, dict)
                    and _inteiro(item.get("numero"), -1, 0) == int(numero)
                )
            ]
            return estado

        await _atualizar_estado(guild_id, aplicar)


async def listar_recompensas_usuario(guild_id: int, user_id: int, limite: int = 20) -> list:
    """Retorna distinções sazonais arquivadas, sem consultar ou alterar XP permanente."""
    estado = await get_estado(guild_id)
    uid = int(user_id)
    conquistas = []
    for temporada in estado["historico"]:
        if not isinstance(temporada, dict):
            continue
        for item in temporada.get("ranking", []):
            if not isinstance(item, dict):
                continue
            try:
                participante = int(item.get("user_id"))
            except (TypeError, ValueError, OverflowError):
                continue
            if participante != uid:
                continue
            posicao = _inteiro(item.get("posicao"), 0, 0)
            if posicao not in (1, 2, 3):
                continue
            recompensas = temporada.get("recompensas", {})
            conquistas.append({
                "temporada": _inteiro(temporada.get("numero"), 0, 0),
                "posicao": posicao,
                "xp_sazonal": _inteiro(item.get("xp"), 0, 0),
                "recompensa": str(recompensas.get(str(posicao), "") or "").strip(),
                "encerrada_em": temporada.get("encerrada_em"),
                "meta_atingida": bool(temporada.get("meta_atingida")),
            })
    conquistas.sort(key=lambda item: item.get("temporada", 0), reverse=True)
    return conquistas[:max(1, min(int(limite), 50))]
