from utils.storage import carregar, salvar

ARQUIVO = "missoes_jogos.json"

JOGOS = {
    "shigaku": {"nome": "Shigaku", "prefixo": "SHI"},
    "gakuran": {"nome": "Gakuran", "prefixo": "GAK"},
    "fistborn": {"nome": "Fistborn", "prefixo": "FIS"},
}


async def obter_dados(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.get(str(guild_id), {})
    if not isinstance(registro, dict):
        registro = {}
    jogos = registro.get("jogos", {})
    registro["jogos"] = jogos if isinstance(jogos, dict) else {}
    return registro


async def salvar_canais(
    guild_id: int,
    jogo: str,
    categoria_missoes_id: int,
    categoria_ranking_id: int,
    missoes_channel_id: int,
    ranking_channel_id: int,
    ranking_message_id: int | None = None,
) -> dict:
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.setdefault(str(guild_id), {})
    jogos = registro.setdefault("jogos", {})
    atual = jogos.setdefault(jogo, {"pontuacao": {}, "eventos_aplicados": []})
    atual.update({
        "nome": JOGOS[jogo]["nome"],
        "categoria_missoes_id": int(categoria_missoes_id),
        "categoria_ranking_id": int(categoria_ranking_id),
        "missoes_channel_id": int(missoes_channel_id),
        "ranking_channel_id": int(ranking_channel_id),
    })
    if ranking_message_id is not None:
        atual["ranking_message_id"] = int(ranking_message_id)
    atual.setdefault("pontuacao", {})
    atual.setdefault("eventos_aplicados", [])
    await salvar(ARQUIVO, todos)
    return atual


async def atualizar_mensagem_ranking(
    guild_id: int, jogo: str, ranking_message_id: int
) -> None:
    todos = await carregar(ARQUIVO, {})
    registro = todos.setdefault(str(guild_id), {})
    jogos = registro.setdefault("jogos", {})
    atual = jogos.setdefault(jogo, {"pontuacao": {}, "eventos_aplicados": []})
    atual["ranking_message_id"] = int(ranking_message_id)
    await salvar(ARQUIVO, todos)


async def registrar_pontos(
    guild_id: int,
    jogo: str,
    user_id: int,
    nome: str,
    pontos: int,
    evento_id: str,
) -> bool:
    if jogo not in JOGOS or int(pontos) <= 0:
        return False
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.get(str(guild_id))
    if not isinstance(registro, dict):
        registro = {}
        todos[str(guild_id)] = registro
    jogos = registro.get("jogos")
    if not isinstance(jogos, dict):
        jogos = {}
        registro["jogos"] = jogos
    atual = jogos.get(jogo)
    if not isinstance(atual, dict):
        atual = {
            "nome": JOGOS[jogo]["nome"],
            "pontuacao": {},
            "eventos_aplicados": [],
        }
        jogos[jogo] = atual

    eventos = atual.get("eventos_aplicados", [])
    if isinstance(eventos, str):
        eventos = [eventos] if eventos.strip() else []
    elif not isinstance(eventos, (list, tuple, set)):
        eventos = []
    eventos = list(dict.fromkeys(str(evento).strip() for evento in eventos if str(evento).strip()))

    chave_evento = str(evento_id or "").strip()
    if not chave_evento or chave_evento in eventos:
        return False

    pontuacao = atual.get("pontuacao")
    if not isinstance(pontuacao, dict):
        pontuacao = {}
        atual["pontuacao"] = pontuacao
    uid = str(user_id)
    perfil = pontuacao.get(uid)
    if not isinstance(perfil, dict):
        perfil = {"nome": nome or "", "pontos": 0}
        pontuacao[uid] = perfil
    if nome:
        perfil["nome"] = nome
    try:
        pontos_atuais = max(0, int(perfil.get("pontos", 0) or 0))
    except (TypeError, ValueError, OverflowError):
        pontos_atuais = 0
    perfil["pontos"] = pontos_atuais + int(pontos)

    eventos.append(chave_evento)
    atual["eventos_aplicados"] = eventos[-5000:]
    await salvar(ARQUIVO, todos)
    return True


async def obter_ranking(guild_id: int, jogo: str, limite: int = 10) -> list:
    registro = await obter_dados(guild_id)
    jogos = registro.get("jogos", {})
    dados_jogo = jogos.get(jogo, {}) if isinstance(jogos, dict) else {}
    if not isinstance(dados_jogo, dict):
        return []
    pontuacao = dados_jogo.get("pontuacao", {})
    if not isinstance(pontuacao, dict):
        return []
    linhas = []
    for uid, perfil in pontuacao.items():
        if not isinstance(perfil, dict):
            continue
        try:
            pontos = max(0, int(perfil.get("pontos", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if pontos > 0:
            linhas.append((str(uid), str(perfil.get("nome") or ""), pontos))
    try:
        limite = max(0, int(limite))
    except (TypeError, ValueError, OverflowError):
        limite = 10
    return sorted(linhas, key=lambda item: (-item[2], item[1].casefold(), item[0]))[:limite]
async def obter_paineis(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO, {})
    registro = todos.get(str(guild_id), {})
    paineis = registro.get("paineis", {}) if isinstance(registro, dict) else {}
    return paineis if isinstance(paineis, dict) else {}

async def salvar_painel(guild_id: int, tipo: str, message_id: int) -> None:
    if tipo not in {"missoes", "ranking"}:
        raise ValueError("Tipo de painel inválido.")
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.setdefault(str(guild_id), {})
    paineis = registro.setdefault("paineis", {})
    paineis[tipo] = int(message_id)
    await salvar(ARQUIVO, todos)


async def obter_estatisticas_jogadores(guild_id: int, user_ids: list[str], jogo: str | None = None) -> dict:
    """Busca estatísticas globais/localizadas para enriquecer o ranking por jogo."""
    from utils.perfis import ARQUIVO_PERFIS
    from utils.competitivo_sync import ARQUIVO_COMPETITIVO

    locais = await carregar(ARQUIVO_PERFIS, {})
    locais_guild = locais.get(str(guild_id), {}) if isinstance(locais, dict) else {}
    competitivo = await carregar(ARQUIVO_COMPETITIVO, {"perfis": {}})
    globais = competitivo.get("perfis", {}) if isinstance(competitivo, dict) else {}
    dados_jogos = await obter_dados(guild_id)
    perfis_jogo = dados_jogos.get("jogos", {}).get(jogo, {}).get("pontuacao", {}) if jogo else {}
    resultado = {}

    for uid in user_ids:
        local = locais_guild.get(str(uid), {}) if isinstance(locais_guild, dict) else {}
        global_ = globais.get(str(uid), {}) if isinstance(globais, dict) else {}
        if not isinstance(local, dict):
            local = {}
        if not isinstance(global_, dict):
            global_ = {}
        kills = int(local.get("kills", global_.get("kills", 0)) or 0)
        deaths = int(local.get("deaths", global_.get("deaths", 0)) or 0)
        perfil_jogo = perfis_jogo.get(str(uid), {}) if isinstance(perfis_jogo, dict) else {}
        if not isinstance(perfil_jogo, dict):
            perfil_jogo = {}
        resultado[str(uid)] = {
            "xp": int(local.get("xp", global_.get("xp", 0)) or 0),
            "vitorias": int(local.get("vitorias", global_.get("vitorias", 0)) or 0),
            "derrotas": int(local.get("derrotas", global_.get("derrotas", 0)) or 0),
            "empates": int(local.get("empates", global_.get("empates", 0)) or 0),
            "kills": kills,
            "deaths": deaths,
            "mvps": int(local.get("mvps", global_.get("mvps", 0)) or 0),
            "sequencia": int(local.get("sequencia_atual", global_.get("sequencia_atual", 0)) or 0),
            "maior_sequencia": int(local.get("maior_sequencia", global_.get("maior_sequencia", 0)) or 0),
            "tempo_top": int(perfil_jogo.get("tempo_top_segundos", 0) or 0),
            "patente": str(local.get("patente", global_.get("patente", "")) or "—"),
            "kdr": round(kills / deaths, 2) if deaths > 0 else float(kills),
        }
    return resultado


async def resetar_pontuacoes_jogos(guild_id: int) -> int:
    """Zera os rankings por jogo junto do reset global, preservando os painéis."""
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.setdefault(str(guild_id), {})
    jogos = registro.setdefault("jogos", {})
    alterados = 0
    for slug in JOGOS:
        atual = jogos.setdefault(slug, {"pontuacao": {}, "eventos_aplicados": []})
        atual["pontuacao"] = {}
        atual["eventos_aplicados"] = []
        atual["ranking_message_id"] = registro.get("paineis", {}).get("ranking")
        alterados += 1
    await salvar(ARQUIVO, todos)
    return alterados


async def atualizar_tempo_top_jogos(guild_id: int, agora: float | None = None) -> None:
    """Acumula tempo no Top 10 de cada jogo, com intervalos limitados a 2 minutos."""
    import time

    agora = float(agora or time.time())
    todos = await carregar(ARQUIVO, {})
    if not isinstance(todos, dict):
        todos = {}
    registro = todos.setdefault(str(guild_id), {})
    jogos = registro.setdefault("jogos", {})
    mudou = False
    for slug in JOGOS:
        dados_jogo = jogos.setdefault(slug, {"pontuacao": {}, "eventos_aplicados": []})
        pontuacao = dados_jogo.setdefault("pontuacao", {})
        ordenados = sorted(
            ((str(uid), perfil) for uid, perfil in pontuacao.items() if isinstance(perfil, dict)),
            key=lambda item: (int(item[1].get("pontos", 0) or 0), str(item[1].get("nome", "")).casefold()),
            reverse=True,
        )
        ids_top = {uid for uid, perfil in ordenados[:10] if int(perfil.get("pontos", 0) or 0) > 0}
        for uid, perfil in pontuacao.items():
            if not isinstance(perfil, dict):
                continue
            ultima = float(perfil.get("ultima_verificacao_top10", agora) or agora)
            decorrido = max(0, min(120, agora - ultima))
            if perfil.get("em_top10"):
                perfil["tempo_top_segundos"] = int(perfil.get("tempo_top_segundos", 0) or 0) + int(decorrido)
            perfil["em_top10"] = str(uid) in ids_top
            perfil["ultima_verificacao_top10"] = agora
            mudou = True
    if mudou:
        await salvar(ARQUIVO, todos)
