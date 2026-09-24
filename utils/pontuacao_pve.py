from utils.storage import carregar
from utils.perfis import get_perfil, _salvar_perfil, ARQUIVO_PERFIS


async def adicionar_pontos(guild_id: int, user_id: int, pontos: int) -> int:
    perfil = await get_perfil(guild_id, user_id)
    perfil["pontos_pve"] = perfil.get("pontos_pve", 0) + pontos
    await _salvar_perfil(guild_id, user_id, perfil)
    return perfil["pontos_pve"]


async def obter_ranking(guild_id: int, limite: int = 10) -> list:
    todos = await carregar(ARQUIVO_PERFIS, {})
    perfis_guild = todos.get(str(guild_id), {})
    pontuados = [(uid, p.get("pontos_pve", 0)) for uid, p in perfis_guild.items() if p.get("pontos_pve", 0) > 0]
    return sorted(pontuados, key=lambda item: item[1], reverse=True)[:limite]