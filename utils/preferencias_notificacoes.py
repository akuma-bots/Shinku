"""Preferências individuais para notificações privadas da NÊMESIS."""
from utils.storage import carregar, salvar

ARQUIVO = "preferencias_notificacoes.json"


async def obter_preferencias(guild_id: int, user_id: int) -> dict:
    dados = await carregar(ARQUIVO, {"guilds": {}})
    usuario = (
        dados.get("guilds", {})
        .get(str(guild_id), {})
        .get(str(user_id), {})
    )
    return {
        "avisos_comunidade": bool(usuario.get("avisos_comunidade", False)),
        "notas_atualizacao": bool(usuario.get("notas_atualizacao", False)),
    }


async def definir_preferencia(
    guild_id: int, user_id: int, categoria: str, habilitada: bool
) -> dict:
    if categoria not in {"avisos_comunidade", "notas_atualizacao"}:
        raise ValueError("Categoria de notificação inválida.")
    dados = await carregar(ARQUIVO, {"guilds": {}})
    if not isinstance(dados, dict):
        dados = {"guilds": {}}
    guilds = dados.setdefault("guilds", {})
    guild = guilds.setdefault(str(guild_id), {})
    usuario = guild.setdefault(str(user_id), {})
    usuario[categoria] = bool(habilitada)
    await salvar(ARQUIVO, dados)
    return await obter_preferencias(guild_id, user_id)


async def listar_inscritos(guild_id: int, categoria: str, membros_ids: list[str] | None = None) -> set[str]:
    """Retorna inscritos; membros sem preferência registrada mantêm o padrão ativo."""
    dados = await carregar(ARQUIVO, {"guilds": {}})
    guild = dados.get("guilds", {}).get(str(guild_id), {})
    if membros_ids is None:
        membros_ids = list(guild)
    return {
        str(user_id)
        for user_id in membros_ids
        if not isinstance(guild.get(str(user_id)), dict)
        or guild[str(user_id)].get(categoria, True) is True
    }
