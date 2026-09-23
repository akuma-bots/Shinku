import random
import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_PVE = "pve.json"  # { guild_id: { "inimigos": [...], "encontros": [...] } }

INIMIGOS_PADRAO = [
    {"nome": "Lobo Sombrio", "dificuldade": "fácil", "recompensa_xp": 20},
    {"nome": "Golem de Pedra", "dificuldade": "médio", "recompensa_xp": 40},
    {"nome": "Dragão Ancião", "dificuldade": "difícil", "recompensa_xp": 80},
]


async def _tudo():
    return await carregar(ARQUIVO_PVE, {})


async def _guild(guild_id: int) -> dict:
    dados = await _tudo()
    return dados.get(str(guild_id), {"inimigos": list(INIMIGOS_PADRAO), "encontros": []})


async def _salvar(guild_id: int, dados_guild: dict):
    dados = await _tudo()
    dados[str(guild_id)] = dados_guild
    await salvar(ARQUIVO_PVE, dados)


async def listar_inimigos(guild_id: int) -> list:
    return (await _guild(guild_id))["inimigos"]


async def adicionar_inimigo(guild_id: int, nome: str, dificuldade: str, recompensa_xp: int):
    dados = await _guild(guild_id)
    dados["inimigos"].append({"nome": nome, "dificuldade": dificuldade, "recompensa_xp": recompensa_xp})
    await _salvar(guild_id, dados)


async def criar_encontro(guild_id: int, user_id: int) -> dict:
    dados = await _guild(guild_id)
    inimigo = random.choice(dados["inimigos"])
    encontro = {
        "id": str(uuid.uuid4())[:8],
        "user_id": user_id,
        "inimigo": inimigo,
        "status": "aberto",
        "timestamp": time.time(),
    }
    dados["encontros"].append(encontro)
    await _salvar(guild_id, dados)
    return encontro


async def get_encontro(guild_id: int, encontro_id: str):
    dados = await _guild(guild_id)
    return next((e for e in dados["encontros"] if e["id"] == encontro_id), None)


async def marcar_status(guild_id: int, encontro_id: str, status: str):
    dados = await _guild(guild_id)
    for e in dados["encontros"]:
        if e["id"] == encontro_id:
            e["status"] = status
    await _salvar(guild_id, dados)