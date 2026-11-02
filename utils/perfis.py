from utils.storage import carregar, salvar, atualizar_json
import time
import uuid
from utils.competitivo_sync import somar_pontos_competitivo


ARQUIVO_PERFIS = "perfis.json"
ARQUIVO_PATENTES = "patentes_config.json"
ARQUIVO_COMPETITIVO = "competitivo.json"


PADRAO_PERFIL = {
    "xp": 0,
    "patente": None,
    "vitorias": 0,
    "derrotas": 0,
    "empates": 0,
    "kills": 0,
    "deaths": 0,
    "mvps": 0,
    "sequencia_atual": 0,
    "maior_sequencia": 0,
    "medalhas": [],
}


XP_VITORIA = 30
XP_DERROTA = 10
XP_BONUS_MVP = 20


def _inteiro_nao_negativo(valor, padrao: int = 0) -> int:
    """Converte estatísticas antigas para inteiros válidos sem deixar o perfil quebrar."""
    try:
        return max(0, int(valor if valor is not None else padrao))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(padrao))


def _normalizar_perfil(perfil) -> dict:
    """Completa campos ausentes e saneia dados legados sem descartar campos extras."""
    if not isinstance(perfil, dict):
        perfil = {}

    normalizado = {**PADRAO_PERFIL, **perfil}
    for campo in (
        "xp",
        "vitorias",
        "derrotas",
        "empates",
        "kills",
        "deaths",
        "mvps",
        "sequencia_atual",
        "maior_sequencia",
    ):
        normalizado[campo] = _inteiro_nao_negativo(
            normalizado.get(campo),
            PADRAO_PERFIL[campo],
        )

    medalhas = normalizado.get("medalhas", [])
    if isinstance(medalhas, str):
        medalhas = [medalhas] if medalhas.strip() else []
    elif not isinstance(medalhas, (list, tuple, set)):
        medalhas = []

    # Preserva a ordem original e remove entradas vazias/duplicadas.
    normalizado["medalhas"] = list(dict.fromkeys(
        str(medalha).strip()
        for medalha in medalhas
        if str(medalha).strip()
    ))

    # Esses registros impedem crédito duplicado após retries/reinicializações.
    # Uma string não pode ser convertida diretamente em lista, pois viraria caracteres.
    for campo in (
        "recompensas_missoes_aplicadas",
        "resultados_pvp_aplicados",
        "sorteios_recompensados",
        "temporadas_bonus_aplicados",
        "eventos_recompensa",
        "resultados_guerra_aplicados",
    ):
        eventos = normalizado.get(campo, [])
        if isinstance(eventos, str):
            eventos = [eventos] if eventos.strip() else []
        elif not isinstance(eventos, (list, tuple, set)):
            eventos = []
        normalizado[campo] = list(dict.fromkeys(
            str(evento).strip()
            for evento in eventos
            if str(evento).strip()
        ))[-5000:]

    normalizado["maior_sequencia"] = max(
        normalizado["maior_sequencia"],
        normalizado["sequencia_atual"],
    )
    return normalizado


async def get_perfil(
    guild_id: int,
    user_id: int,
) -> dict:
    todos = await carregar(ARQUIVO_PERFIS, {})
    guilds = todos if isinstance(todos, dict) else {}
    perfis_guild = guilds.get(str(guild_id), {})
    if not isinstance(perfis_guild, dict):
        perfis_guild = {}
    perfil = perfis_guild.get(str(user_id), {})

    # Recupera estatísticas antigas do ranking interno se o perfil local ainda não existir.
    if not isinstance(perfil, dict) or not perfil:
        competitivo = await carregar(
            ARQUIVO_COMPETITIVO,
            {"catalogo": [], "perfis": {}},
        )
        competitivos = competitivo.get("perfis", {}) if isinstance(competitivo, dict) else {}
        perfil_competitivo = competitivos.get(str(user_id), {}) if isinstance(competitivos, dict) else {}
        if isinstance(perfil_competitivo, dict) and perfil_competitivo:
            perfil = {
                chave: perfil_competitivo[chave]
                for chave in PADRAO_PERFIL
                if chave in perfil_competitivo
            }

    return _normalizar_perfil(perfil)


async def atualizar_perfil(
    guild_id: int,
    user_id: int,
    transformador,
    perfil_inicial: dict = None,
) -> dict:
    """Atualiza um perfil na versão mais recente do documento, com CAS no Redis."""
    chave_guild = str(guild_id)
    chave_usuario = str(user_id)
    if perfil_inicial is None:
        # Preserva perfis migrados do ranking competitivo quando ainda não
        # existe um registro local em perfis.json.
        perfil_inicial = await get_perfil(guild_id, user_id)

    def aplicar(documento):
        if not isinstance(documento, dict):
            documento = {}
        guild = documento.get(chave_guild)
        if not isinstance(guild, dict):
            guild = {}
        atual = _normalizar_perfil(guild.get(chave_usuario, perfil_inicial or {}))
        novo = transformador(atual)
        guild[chave_usuario] = _normalizar_perfil(novo if isinstance(novo, dict) else atual)
        documento[chave_guild] = guild
        return documento

    atualizado = await atualizar_json(ARQUIVO_PERFIS, {}, aplicar)
    guild = atualizado.get(chave_guild, {})
    perfil = guild.get(chave_usuario, {}) if isinstance(guild, dict) else {}
    return _normalizar_perfil(perfil)


async def resetar_perfis_globais(
    agora: float = None,
    operation_id: str = None,
) -> dict:
    """Zera estatísticas locais e competitivas, preservando identidades e catálogo.

    Cada documento recebe o identificador da operação. Se a execução cair
    entre os dois arquivos, repetir com o mesmo operation_id conclui apenas
    a parte que ainda não foi persistida.
    """
    agora = float(agora or time.time())
    operation_id = str(operation_id or uuid.uuid4().hex)
    campos_zero = {
        "xp": 0,
        "pontos_pve": 0,
        "vitorias": 0,
        "derrotas": 0,
        "empates": 0,
        "kills": 0,
        "deaths": 0,
        "mvps": 0,
        "sequencia_atual": 0,
        "maior_sequencia": 0,
        "medalhas": [],
        "patente": None,
        "recompensas_missoes_aplicadas": [],
        "resultados_pvp_aplicados": [],
        "resultados_guerra_aplicados": [],
        "sorteios_recompensados": [],
        "temporadas_bonus_aplicados": [],
        "eventos_recompensa": [],
    }
    contagem_local = {"valor": 0}

    def resetar_local(dados):
        if not isinstance(dados, dict):
            dados = {}
        meta = dados.get("_nemesis_meta")
        if not isinstance(meta, dict):
            meta = {}
        if meta.get("ultimo_reset_global_id") == operation_id:
            return dados

        quantidade = 0
        for guild_id, perfis_guild in dados.items():
            if guild_id == "_nemesis_meta" or not isinstance(perfis_guild, dict):
                continue
            for perfil in perfis_guild.values():
                if not isinstance(perfil, dict):
                    continue
                for campo, valor in campos_zero.items():
                    perfil[campo] = list(valor) if isinstance(valor, list) else valor
                quantidade += 1
        meta["ultimo_reset_global_id"] = operation_id
        meta["ultimo_reset_global_em"] = agora
        dados["_nemesis_meta"] = meta
        contagem_local["valor"] = quantidade
        return dados

    await atualizar_json(ARQUIVO_PERFIS, {}, resetar_local)

    contagem_competitiva = {"valor": 0}

    def resetar_competitivo(dados):
        if not isinstance(dados, dict):
            dados = {"catalogo": [], "perfis": {}}
        if not isinstance(dados.get("catalogo"), list):
            dados["catalogo"] = []
        if not isinstance(dados.get("perfis"), dict):
            dados["perfis"] = {}
        meta = dados.get("_nemesis_meta")
        if not isinstance(meta, dict):
            meta = {}
        if meta.get("ultimo_reset_global_id") == operation_id:
            return dados

        quantidade = 0
        for perfil in dados["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil.update({
                "pontos": 0,
                "pontos_temporada": 0,
                "xp": 0,
                "vitorias": 0,
                "derrotas": 0,
                "kills": 0,
                "deaths": 0,
                "mvps": 0,
                "sequencia_atual": 0,
                "maior_sequencia": 0,
                "medalhas": [],
                "patente": None,
                "kdr": 0,
                "tempo_top_global_segundos": 0,
                "em_top_global": False,
                "ultima_verificacao_top_global": agora,
                "eventos_pontos_aplicados": [],
            })
            quantidade += 1

        dados["temporada_global"] = {
            "numero": 1,
            "inicio_timestamp": agora,
            "duracao_dias": 30,
            "historico": [],
        }
        meta["ultimo_reset_global_id"] = operation_id
        meta["ultimo_reset_global_em"] = agora
        dados["_nemesis_meta"] = meta
        contagem_competitiva["valor"] = quantidade
        return dados

    await atualizar_json(
        ARQUIVO_COMPETITIVO, {"catalogo": [], "perfis": {}}, resetar_competitivo
    )
    return {
        "quantidade_local": contagem_local["valor"],
        "quantidade_global": contagem_competitiva["valor"],
        "operation_id": operation_id,
    }


async def _salvar_perfil(
    guild_id: int,
    user_id: int,
    perfil: dict,
):
    return await atualizar_perfil(
        guild_id, user_id, lambda _atual: perfil
    )


async def _atualizar_ranking_competitivo(
    user_id: int,
    perfil: dict,
    nome: str = "",
    delta_pontos: int = 0,  # mantido por compatibilidade; P.C. não é mais pontuado
    evento_id: str = "",
) -> dict:
    """Sincroniza o perfil competitivo no mesmo commit atômico da pontuação."""
    kills = int(perfil.get("kills", 0) or 0)
    deaths = int(perfil.get("deaths", 0) or 0)
    campos_extra = {
        "xp": int(perfil.get("xp", 0) or 0),
        "kills": kills,
        "deaths": deaths,
        "mvps": int(perfil.get("mvps", 0) or 0),
        "sequencia_atual": int(perfil.get("sequencia_atual", 0) or 0),
        "maior_sequencia": int(perfil.get("maior_sequencia", 0) or 0),
        "patente": perfil.get("patente"),
        "medalhas": list(perfil.get("medalhas", [])),
        "kdr": round(kills / deaths, 2) if deaths > 0 else float(kills),
    }
    return await somar_pontos_competitivo(
        user_id=user_id,
        nome=nome,
        delta=0,
        vitorias=perfil.get("vitorias", 0),
        derrotas=perfil.get("derrotas", 0),
        evento_id=evento_id,
        campos_extra=campos_extra,
    )


async def get_patentes(
    guild_id: int,
) -> list:

    todas = await carregar(
        ARQUIVO_PATENTES,
        {},
    )

    lista = todas.get(
        str(guild_id),
        [],
    )

    return sorted(
        lista,
        key=lambda p: p["xp_minimo"],
    )


async def salvar_patentes(
    guild_id: int,
    lista: list,
):

    todas = await carregar(
        ARQUIVO_PATENTES,
        {},
    )

    todas[str(guild_id)] = lista

    await salvar(
        ARQUIVO_PATENTES,
        todas,
    )


def _checar_novas_medalhas(
    perfil: dict,
) -> list:

    candidatas = []

    if perfil["vitorias"] == 1:
        candidatas.append(
            "🥉 Primeira Vitória"
        )

    if perfil["vitorias"] >= 10:
        candidatas.append(
            "🥈 Veterano (10 vitórias)"
        )

    if perfil["vitorias"] >= 50:
        candidatas.append(
            "🥇 Lenda (50 vitórias)"
        )

    if perfil["mvps"] >= 5:
        candidatas.append(
            "⭐ MVP Frequente (5 MVPs)"
        )

    if perfil["maior_sequencia"] >= 5:
        candidatas.append(
            "🔥 Sequência de 5"
        )

    if perfil["maior_sequencia"] >= 10:
        candidatas.append(
            "🔥🔥 Sequência de 10"
        )

    return [
        medalha
        for medalha in candidatas
        if medalha not in perfil["medalhas"]
    ]


async def registrar_resultado_guerra(
    guild_id: int,
    user_id: int,
    venceu: bool,
    foi_mvp: bool = False,
    evento_id: str = "",
) -> dict:
    """Registra o resultado uma única vez quando recebe uma chave de evento."""
    estado = {"patente_antiga": None, "medalhas_novas": []}
    evento_id = str(evento_id or "").strip()

    def aplicar(perfil):
        estado["patente_antiga"] = perfil.get("patente")
        eventos = perfil.setdefault("resultados_guerra_aplicados", [])
        if evento_id and evento_id in eventos:
            estado["medalhas_novas"] = []
            return perfil
        if evento_id:
            eventos.append(evento_id)
            perfil["resultados_guerra_aplicados"] = eventos[-1000:]

        if venceu:
            perfil["vitorias"] += 1
            perfil["sequencia_atual"] += 1
            perfil["maior_sequencia"] = max(
                perfil["maior_sequencia"], perfil["sequencia_atual"]
            )
            perfil["xp"] += XP_VITORIA
        else:
            perfil["derrotas"] += 1
            perfil["sequencia_atual"] = 0
            perfil["xp"] += XP_DERROTA
        if foi_mvp:
            perfil["mvps"] += 1
            perfil["xp"] += XP_BONUS_MVP

        novas = _checar_novas_medalhas(perfil)
        perfil["medalhas"].extend(novas)
        estado["medalhas_novas"] = novas
        return perfil

    perfil = await atualizar_perfil(guild_id, user_id, aplicar)
    delta_pontos = (
        (XP_VITORIA if venceu else XP_DERROTA)
        + (10 if venceu else 0)
        + (XP_BONUS_MVP if foi_mvp else 0)
    )
    competitivo = await _atualizar_ranking_competitivo(
        user_id=user_id,
        perfil=perfil,
        delta_pontos=delta_pontos,
        evento_id=evento_id,
    )
    return {
        "perfil": perfil,
        "competitivo": competitivo,
        "medalhas_novas": estado["medalhas_novas"],
        "patente_antiga": estado["patente_antiga"],
    }

async def registrar_empate_guerra(
    guild_id: int,
    user_id: int,
    foi_mvp: bool = False,
    evento_id: str = "",
) -> dict:
    """Registra empate de forma atômica e idempotente quando há evento_id."""
    estado = {"patente_antiga": None, "medalhas_novas": []}
    evento_id = str(evento_id or "").strip()

    def aplicar(perfil):
        estado["patente_antiga"] = perfil.get("patente")
        eventos = perfil.setdefault("resultados_guerra_aplicados", [])
        if evento_id and evento_id in eventos:
            estado["medalhas_novas"] = []
            return perfil
        if evento_id:
            eventos.append(evento_id)
            perfil["resultados_guerra_aplicados"] = eventos[-1000:]
        perfil["empates"] += 1
        perfil["sequencia_atual"] = 0
        perfil["xp"] += 15
        if foi_mvp:
            perfil["mvps"] += 1
            perfil["xp"] += XP_BONUS_MVP
        novas = _checar_novas_medalhas(perfil)
        perfil["medalhas"].extend(novas)
        estado["medalhas_novas"] = novas
        return perfil

    perfil = await atualizar_perfil(guild_id, user_id, aplicar)
    competitivo = await _atualizar_ranking_competitivo(
        user_id=user_id,
        perfil=perfil,
        delta_pontos=15 + (XP_BONUS_MVP if foi_mvp else 0),
        evento_id=evento_id,
    )
    return {
        "perfil": perfil,
        "competitivo": competitivo,
        "medalhas_novas": estado["medalhas_novas"],
        "patente_antiga": estado["patente_antiga"],
    }

async def registrar_pvp(
    guild_id: int,
    vencedor_id: int,
    perdedor_id: int,
    evento_id: str = "",
) -> tuple:
    evento_id = str(evento_id or "").strip()

    def aplicar_vitoria(perfil):
        eventos = perfil.setdefault("resultados_pvp_aplicados", [])
        chave = f"{evento_id}:vitoria" if evento_id else ""
        if chave and chave in eventos:
            return perfil
        perfil["kills"] += 1
        if chave:
            eventos.append(chave)
            perfil["resultados_pvp_aplicados"] = eventos[-1000:]
        return perfil

    def aplicar_derrota(perfil):
        eventos = perfil.setdefault("resultados_pvp_aplicados", [])
        chave = f"{evento_id}:derrota" if evento_id else ""
        if chave and chave in eventos:
            return perfil
        perfil["deaths"] += 1
        if chave:
            eventos.append(chave)
            perfil["resultados_pvp_aplicados"] = eventos[-1000:]
        return perfil

    perfil_vencedor = await atualizar_perfil(guild_id, vencedor_id, aplicar_vitoria)
    perfil_perdedor = await atualizar_perfil(guild_id, perdedor_id, aplicar_derrota)
    await _atualizar_ranking_competitivo(
        user_id=vencedor_id, perfil=perfil_vencedor, delta_pontos=0
    )
    await _atualizar_ranking_competitivo(
        user_id=perdedor_id, perfil=perfil_perdedor, delta_pontos=0
    )
    return perfil_vencedor, perfil_perdedor

async def calcular_patente_atual(
    guild_id: int,
    xp: int,
):

    patentes = await get_patentes(
        guild_id
    )

    atingida = None

    for patente in patentes:

        if xp >= patente["xp_minimo"]:
            atingida = patente

    return atingida


async def definir_patente(
    guild_id: int,
    user_id: int,
    nome_patente: str,
):
    perfil = await atualizar_perfil(
        guild_id, user_id,
        lambda atual: {**atual, "patente": nome_patente},
    )
    await _atualizar_ranking_competitivo(
        user_id=user_id, perfil=perfil, delta_pontos=0,
    )
    return perfil


def kdr(perfil: dict) -> float:
    if perfil["deaths"] > 0:
        return round(perfil["kills"] / perfil["deaths"], 2)
    return float(perfil["kills"])
