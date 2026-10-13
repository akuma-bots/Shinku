from utils.storage import carregar, salvar

ARQUIVO_COMPETITIVO = "competitivo.json"

PADRAO_COMPETITIVO = {
    "catalogo": [],
    "perfis": {},
}


DURACAO_TEMPORADA_SEGUNDOS = 30 * 24 * 60 * 60
LIMITE_TOP_GLOBAL = 10


async def atualizar_temporada_global(agora: float | None = None) -> dict:
    """
    Mantém a temporada global no mesmo competitivo.json consumido pelo site.
    A cada 30 dias arquiva o Top 10 e zera somente a pontuação sazonal.
    """
    import time

    agora = float(agora or time.time())
    dados = await carregar(ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO.copy())
    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})
    estado = dados.get("temporada_global") or {}

    if not estado.get("inicio_timestamp"):
        estado = {
            "numero": int(estado.get("numero", 1) or 1),
            "inicio_timestamp": agora,
            "duracao_dias": 30,
            "historico": estado.get("historico", []) or [],
        }
        for perfil in dados["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil.setdefault("pontos_temporada", int(perfil.get("pontos", 0) or 0))
            perfil.setdefault("tempo_top_global_segundos", 0)
            perfil.setdefault("em_top_global", False)
            perfil.setdefault("ultima_verificacao_top_global", agora)
        dados["temporada_global"] = estado
        await salvar(ARQUIVO_COMPETITIVO, dados)
        return dados

    inicio = float(estado["inicio_timestamp"])
    duracao = max(1, int(estado.get("duracao_dias", 30) or 30)) * 86400
    if agora - inicio >= duracao:
        ordenados = sorted(
            (
                (str(uid), perfil)
                for uid, perfil in dados["perfis"].items()
                if isinstance(perfil, dict)
            ),
            key=lambda item: (
                int(item[1].get("pontos_temporada", item[1].get("pontos", 0)) or 0),
                int(item[1].get("vitorias", 0) or 0),
            ),
            reverse=True,
        )
        historico = estado.setdefault("historico", [])
        historico.append({
            "numero": int(estado.get("numero", 1) or 1),
            "inicio_timestamp": inicio,
            "fim_timestamp": agora,
            "top": [
                {
                    "discordId": uid,
                    "nome": perfil.get("nome", ""),
                    "pontos": int(perfil.get("pontos_temporada", perfil.get("pontos", 0)) or 0),
                    "xp": int(perfil.get("xp", 0) or 0),
                    "vitorias": int(perfil.get("vitorias", 0) or 0),
                    "derrotas": int(perfil.get("derrotas", 0) or 0),
                }
                for uid, perfil in ordenados[:LIMITE_TOP_GLOBAL]
            ],
        })
        estado["numero"] = int(estado.get("numero", 1) or 1) + 1
        # Avança por blocos de 30 dias sem perder o alinhamento se o bot ficou offline.
        estado["inicio_timestamp"] = inicio + (int((agora - inicio) // duracao) * duracao)
        estado["duracao_dias"] = 30
        for perfil in dados["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil["pontos_temporada"] = 0
            perfil["em_top_global"] = False
            perfil["ultima_verificacao_top_global"] = agora
    for perfil in dados["perfis"].values():
        if not isinstance(perfil, dict):
            continue
        perfil.setdefault("pontos_temporada", int(perfil.get("pontos", 0) or 0))
        perfil.setdefault("tempo_top_global_segundos", 0)
        perfil.setdefault("em_top_global", False)
        perfil.setdefault("ultima_verificacao_top_global", agora)
    dados["temporada_global"] = estado
    await salvar(ARQUIVO_COMPETITIVO, dados)
    return dados


async def reiniciar_temporada_global(agora: float | None = None) -> dict:
    """Fecha a temporada atual e inicia outra sem apagar estatísticas acumuladas."""
    import time

    agora = float(agora or time.time())
    dados = await carregar(ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO.copy())
    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})
    estado = dados.get("temporada_global") or {}
    inicio = float(estado.get("inicio_timestamp") or agora)
    numero_atual = int(estado.get("numero", 1) or 1)

    ordenados = sorted(
        (
            (str(uid), perfil)
            for uid, perfil in dados["perfis"].items()
            if isinstance(perfil, dict)
        ),
        key=lambda item: (
            int(item[1].get("pontos_temporada", item[1].get("pontos", 0)) or 0),
            int(item[1].get("vitorias", 0) or 0),
        ),
        reverse=True,
    )

    historico = estado.setdefault("historico", [])
    historico.append({
        "numero": numero_atual,
        "inicio_timestamp": inicio,
        "fim_timestamp": agora,
        "top": [
            {
                "discordId": uid,
                "nome": perfil.get("nome", ""),
                "pontos": int(perfil.get("pontos_temporada", perfil.get("pontos", 0)) or 0),
                "xp": int(perfil.get("xp", 0) or 0),
                "vitorias": int(perfil.get("vitorias", 0) or 0),
                "derrotas": int(perfil.get("derrotas", 0) or 0),
            }
            for uid, perfil in ordenados[:LIMITE_TOP_GLOBAL]
        ],
    })

    estado.update({
        "numero": numero_atual + 1,
        "inicio_timestamp": agora,
        "duracao_dias": 30,
        "historico": historico,
    })

    for perfil in dados["perfis"].values():
        if not isinstance(perfil, dict):
            continue
        perfil["pontos_temporada"] = 0
        perfil["em_top_global"] = False
        perfil["ultima_verificacao_top_global"] = agora
        perfil.setdefault("tempo_top_global_segundos", 0)

    dados["temporada_global"] = estado
    await salvar(ARQUIVO_COMPETITIVO, dados)
    return dados


async def registrar_tempo_top_global(agora: float | None = None, limite: int = 10) -> dict:
    """Acumula tempo apenas durante intervalos em que o perfil permaneceu no Top 10."""
    import time

    agora = float(agora or time.time())
    dados = await atualizar_temporada_global(agora)
    perfis = dados.get("perfis", {})
    ordenados = sorted(
        (
            (str(uid), perfil)
            for uid, perfil in perfis.items()
            if isinstance(perfil, dict)
        ),
        key=lambda item: (
            int(item[1].get("pontos_temporada", item[1].get("pontos", 0)) or 0),
            int(item[1].get("vitorias", 0) or 0),
        ),
        reverse=True,
    )
    ids_top = {uid for uid, _ in ordenados[:limite]}
    for uid, perfil in perfis.items():
        if not isinstance(perfil, dict):
            continue
        ultima = float(perfil.get("ultima_verificacao_top_global", agora) or agora)
        decorrido = max(0, min(120, agora - ultima))
        if perfil.get("em_top_global"):
            perfil["tempo_top_global_segundos"] = int(
                perfil.get("tempo_top_global_segundos", 0) or 0
            ) + int(decorrido)
        perfil["em_top_global"] = str(uid) in ids_top
        perfil["ultima_verificacao_top_global"] = agora
    await salvar(ARQUIVO_COMPETITIVO, dados)
    return dados


async def somar_pontos_competitivo(
    user_id: int,
    nome: str = "",
    delta: int = 0,
    vitorias: int | None = None,
    derrotas: int | None = None,
    evento_id: str = "",
) -> dict:
    """
    Atualiza o mesmo competitivo.json usado pelo Dashboard da NÊMESIS.

    O delta é somado à pontuação existente. Assim, alterações feitas
    manualmente pelo Dashboard não são sobrescritas pelo bot.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        PADRAO_COMPETITIVO.copy(),
    )

    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})

    chave = str(user_id)

    perfil = dados["perfis"].get(chave) or {
        "discordId": chave,
        "nome": nome or "",
        "pontos": 0,
        "elo": 1000,
        "vitorias": 0,
        "derrotas": 0,
    }

    perfil["discordId"] = chave

    if nome:
        perfil["nome"] = nome

    eventos = perfil.get("eventos_pontos_aplicados", [])
    if not isinstance(eventos, list):
        eventos = []
    evento_id = str(evento_id or "").strip()
    delta_efetivo = int(delta)
    if evento_id:
        if evento_id in eventos:
            delta_efetivo = 0
        else:
            eventos.append(evento_id)
            perfil["eventos_pontos_aplicados"] = eventos[-1000:]

    pontos_anteriores = int(perfil.get("pontos", 0) or 0)
    perfil["pontos"] = pontos_anteriores + delta_efetivo
    perfil["pontos_temporada"] = (
        int(perfil.get("pontos_temporada", pontos_anteriores) or 0)
        + delta_efetivo
    )
    perfil.setdefault("tempo_top_global_segundos", 0)
    perfil.setdefault("em_top_global", False)

    if vitorias is not None:
        perfil["vitorias"] = int(vitorias)

    if derrotas is not None:
        perfil["derrotas"] = int(derrotas)

    dados["perfis"][chave] = perfil

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )

    return perfil


async def migrar_perfil_se_necessario(
    user_id: int,
    nome: str,
    perfil_bot: dict,
) -> dict:
    """
    Migra um perfil antigo do perfis.json para competitivo.json
    somente se ele ainda não existir no ranking compartilhado.

    Se o usuário já tiver perfil criado pelo site, nada é sobrescrito.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        PADRAO_COMPETITIVO.copy(),
    )

    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})

    chave = str(user_id)

    if chave in dados["perfis"]:
        return dados["perfis"][chave]

    pontos = (
        int(perfil_bot.get("xp", 0) or 0)
        + int(perfil_bot.get("vitorias", 0) or 0) * 10
        + int(perfil_bot.get("mvps", 0) or 0) * 20
    )

    perfil = {
        "discordId": chave,
        "nome": nome or "",
        "pontos": pontos,
        "elo": 1000,
        "vitorias": int(
            perfil_bot.get("vitorias", 0) or 0
        ),
        "derrotas": int(
            perfil_bot.get("derrotas", 0) or 0
        ),
        "xp": int(perfil_bot.get("xp", 0) or 0),
        "pontos_temporada": pontos,
        "tempo_top_global_segundos": 0,
        "em_top_global": False,
    }

    dados["perfis"][chave] = perfil

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )

    return perfil