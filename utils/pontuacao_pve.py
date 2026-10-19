import asyncio

from utils.storage import carregar
from utils.perfis import get_perfil, _salvar_perfil, ARQUIVO_PERFIS


_PVE_LOCK = asyncio.Lock()


async def adicionar_pontos(guild_id: int, user_id: int, pontos: int) -> int:
    try:
        pontos = int(pontos)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("A pontuação PvE precisa ser um número inteiro válido.") from erro
    if pontos < 0:
        raise ValueError("A pontuação PvE não pode ser negativa.")

    async with _PVE_LOCK:
        perfil = await get_perfil(guild_id, user_id)
        try:
            atual = max(0, int(perfil.get("pontos_pve", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            atual = 0
        perfil["pontos_pve"] = atual + pontos
        await _salvar_perfil(guild_id, user_id, perfil)
        return perfil["pontos_pve"]


async def obter_ranking(guild_id: int, limite: int = 10) -> list:
    todos = await carregar(ARQUIVO_PERFIS, {})
    if not isinstance(todos, dict):
        return []
    perfis_guild = todos.get(str(guild_id), {})
    if not isinstance(perfis_guild, dict):
        return []

    pontuados = []
    for uid, perfil in perfis_guild.items():
        if not isinstance(perfil, dict):
            continue
        try:
            pontos = max(0, int(perfil.get("pontos_pve", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if pontos > 0:
            pontuados.append((str(uid), pontos))

    try:
        limite = max(0, int(limite))
    except (TypeError, ValueError, OverflowError):
        limite = 10
    return sorted(pontuados, key=lambda item: (-item[1], item[0]))[:limite]
