from utils.storage import carregar, salvar

ARQUIVO = "missoes_jogos.json"

JOGOS = {
    "shigaku": {"nome": "Shigaku", "prefixo": "SHI"},
    "gakuran": {"nome": "Gakuran", "prefixo": "GAK"},
    "fistborn": {"nome": "Fistborn", "prefixo": "FIS"},
}


async def obter_dados(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO, {})
    registro = todos.get(str(guild_id), {})
    if not isinstance(registro, dict):
        registro = {}
    registro.setdefault("jogos", {})
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
    registro = todos.setdefault(str(guild_id), {})
    jogos = registro.setdefault("jogos", {})
    atual = jogos.setdefault(jogo, {
        "nome": JOGOS[jogo]["nome"],
        "pontuacao": {},
        "eventos_aplicados": [],
    })
    eventos = atual.setdefault("eventos_aplicados", [])
    chave_evento = str(evento_id or "").strip()
    if not chave_evento or chave_evento in eventos:
        return False
    pontuacao = atual.setdefault("pontuacao", {})
    uid = str(user_id)
    perfil = pontuacao.setdefault(uid, {"nome": nome or "", "pontos": 0})
    if nome:
        perfil["nome"] = nome
    perfil["pontos"] = int(perfil.get("pontos", 0) or 0) + int(pontos)
    eventos.append(chave_evento)
    atual["eventos_aplicados"] = eventos[-5000:]
    await salvar(ARQUIVO, todos)
    return True


async def obter_ranking(guild_id: int, jogo: str, limite: int = 10) -> list:
    registro = await obter_dados(guild_id)
    dados_jogo = registro.get("jogos", {}).get(jogo, {})
    pontuacao = dados_jogo.get("pontuacao", {})
    linhas = []
    for uid, perfil in pontuacao.items():
        if not isinstance(perfil, dict):
            continue
        pontos = int(perfil.get("pontos", 0) or 0)
        if pontos > 0:
            linhas.append((str(uid), str(perfil.get("nome") or ""), pontos))
    return sorted(linhas, key=lambda item: (item[2], item[1].casefold()), reverse=True)[:limite]
