from utils.storage import carregar, salvar, atualizar_json

ARQUIVO_COMPETITIVO = "competitivo.json"

PADRAO_COMPETITIVO = {
    "catalogo": [],
    "perfis": {},
}


DURACAO_TEMPORADA_SEGUNDOS = 30 * 24 * 60 * 60
LIMITE_TOP_GLOBAL = 10


async def atualizar_temporada_global(agora: float | None = None) -> dict:
    """Inicializa/encerra a temporada global em uma única atualização atômica."""
    import time

    agora = float(agora or time.time())

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {"catalogo": [], "perfis": {}}
        if not isinstance(dados.get("catalogo"), list):
            dados["catalogo"] = []
        if not isinstance(dados.get("perfis"), dict):
            dados["perfis"] = {}
        estado = dados.get("temporada_global")
        if not isinstance(estado, dict):
            estado = {}

        if not estado.get("inicio_timestamp"):
            estado = {
                "numero": max(1, int(estado.get("numero", 1) or 1)),
                "inicio_timestamp": agora,
                "duracao_dias": 30,
                "historico": estado.get("historico", []) if isinstance(estado.get("historico"), list) else [],
            }
        else:
            inicio = float(estado["inicio_timestamp"])
            duracao_dias = max(1, int(estado.get("duracao_dias", 30) or 30))
            duracao = duracao_dias * 86400
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
                historico = estado.get("historico", [])
                if not isinstance(historico, list):
                    historico = []
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
                estado.update({
                    "numero": int(estado.get("numero", 1) or 1) + 1,
                    "inicio_timestamp": inicio + (int((agora - inicio) // duracao) * duracao),
                    "duracao_dias": 30,
                    "historico": historico[-1000:],
                })
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
        return dados

    return await atualizar_json(ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO, aplicar)


async def reiniciar_temporada_global(
    agora: float | None = None,
    numero_esperado: int | None = None,
) -> dict:
    """Fecha a temporada atual e inicia outra sem apagar estatísticas acumuladas.

    numero_esperado permite que uma confirmação antiga não reinicie uma
    temporada diferente caso duas interações ocorram quase ao mesmo tempo.
    """
    import time

    agora = float(agora or time.time())

    aplicado = {"valor": False}

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {"catalogo": [], "perfis": {}}
        if not isinstance(dados.get("catalogo"), list):
            dados["catalogo"] = []
        if not isinstance(dados.get("perfis"), dict):
            dados["perfis"] = {}
        estado = dados.get("temporada_global")
        if not isinstance(estado, dict):
            estado = {}
        numero_atual = max(1, int(estado.get("numero", 1) or 1))
        if numero_esperado is not None and numero_atual != int(numero_esperado):
            aplicado["valor"] = False
            return dados

        aplicado["valor"] = True
        inicio = float(estado.get("inicio_timestamp") or agora)
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
        historico = estado.get("historico", [])
        if not isinstance(historico, list):
            historico = []
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
            "historico": historico[-1000:],
        })
        for perfil in dados["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil["pontos_temporada"] = 0
            perfil["em_top_global"] = False
            perfil["ultima_verificacao_top_global"] = agora
            perfil.setdefault("tempo_top_global_segundos", 0)
        dados["temporada_global"] = estado
        return dados

    dados = await atualizar_json(ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO, aplicar)
    dados["_reinicio_aplicado"] = aplicado["valor"]
    return dados


async def registrar_tempo_top_global(
    agora: float | None = None,
    limite: int = 10,
) -> dict:
    """Acumula permanência no Top 10 em uma atualização atômica."""
    import time

    agora = float(agora or time.time())
    limite = max(0, int(limite))
    await atualizar_temporada_global(agora)

    def aplicar(dados):
        perfis = dados.get("perfis", {})
        if not isinstance(perfis, dict):
            perfis = {}
            dados["perfis"] = perfis
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
            try:
                ultima = float(perfil.get("ultima_verificacao_top_global", agora) or agora)
            except (TypeError, ValueError, OverflowError):
                ultima = agora
            decorrido = max(0, min(120, agora - ultima))
            if perfil.get("em_top_global"):
                perfil["tempo_top_global_segundos"] = int(
                    perfil.get("tempo_top_global_segundos", 0) or 0
                ) + int(decorrido)
            perfil["em_top_global"] = str(uid) in ids_top
            perfil["ultima_verificacao_top_global"] = agora
        return dados

    return await atualizar_json(ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO, aplicar)


async def somar_pontos_competitivo(
    user_id: int,
    nome: str = "",
    delta: int = 0,
    vitorias: int | None = None,
    derrotas: int | None = None,
    evento_id: str = "",
    campos_extra: dict = None,
) -> dict:
    """Atualiza o perfil competitivo atomicamente e evita reaplicar eventos."""
    chave = str(user_id)
    evento_id = str(evento_id or "").strip()
    delta = int(delta)

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {"catalogo": [], "perfis": {}}
        if not isinstance(dados.get("catalogo"), list):
            dados["catalogo"] = []
        if not isinstance(dados.get("perfis"), dict):
            dados["perfis"] = {}

        perfil = dados["perfis"].get(chave)
        if not isinstance(perfil, dict):
            perfil = {
                "discordId": chave, "nome": nome or "", "pontos": 0,
                "elo": 1000, "vitorias": 0, "derrotas": 0,
            }
        perfil["discordId"] = chave
        if nome:
            perfil["nome"] = nome

        eventos = perfil.get("eventos_pontos_aplicados", [])
        if isinstance(eventos, str):
            eventos = [eventos] if eventos.strip() else []
        elif not isinstance(eventos, list):
            eventos = []
        delta_efetivo = delta
        if evento_id:
            if evento_id in eventos:
                delta_efetivo = 0
            else:
                eventos.append(evento_id)
            perfil["eventos_pontos_aplicados"] = eventos[-1000:]

        pontos_anteriores = int(perfil.get("pontos", 0) or 0)
        pontos_temporada = int(
            perfil.get("pontos_temporada", pontos_anteriores) or 0
        )
        perfil["pontos"] = pontos_anteriores + delta_efetivo
        perfil["pontos_temporada"] = pontos_temporada + delta_efetivo
        perfil.setdefault("tempo_top_global_segundos", 0)
        perfil.setdefault("em_top_global", False)
        if vitorias is not None:
            perfil["vitorias"] = int(vitorias)
        if derrotas is not None:
            perfil["derrotas"] = int(derrotas)
        if isinstance(campos_extra, dict):
            perfil.update(campos_extra)

        dados["perfis"][chave] = perfil
        return dados

    dados = await atualizar_json(
        ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO, aplicar
    )
    return dados["perfis"][chave]


async def migrar_perfil_se_necessario(
    user_id: int,
    nome: str,
    perfil_bot: dict,
) -> dict:
    """Migra perfil legado apenas se o registro ainda não existir, usando CAS."""
    chave = str(user_id)

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {"catalogo": [], "perfis": {}}
        if not isinstance(dados.get("catalogo"), list):
            dados["catalogo"] = []
        if not isinstance(dados.get("perfis"), dict):
            dados["perfis"] = {}
        if chave in dados["perfis"]:
            return dados

        pontos = (
            int(perfil_bot.get("xp", 0) or 0)
            + int(perfil_bot.get("vitorias", 0) or 0) * 10
            + int(perfil_bot.get("mvps", 0) or 0) * 20
        )
        dados["perfis"][chave] = {
            "discordId": chave,
            "nome": nome or "",
            "pontos": pontos,
            "elo": 1000,
            "vitorias": int(perfil_bot.get("vitorias", 0) or 0),
            "derrotas": int(perfil_bot.get("derrotas", 0) or 0),
            "xp": int(perfil_bot.get("xp", 0) or 0),
            "pontos_temporada": pontos,
            "tempo_top_global_segundos": 0,
            "em_top_global": False,
        }
        return dados

    dados = await atualizar_json(
        ARQUIVO_COMPETITIVO, PADRAO_COMPETITIVO, aplicar
    )
    return dados["perfis"][chave]
