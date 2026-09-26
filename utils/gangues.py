import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_GANGUES = "gangues.json"  # { guild_id: [ {gangue...}, ... ] }


async def _tudo():
    return await carregar(ARQUIVO_GANGUES, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_GANGUES, dados)


async def listar(guild_id: int) -> list:
    return (await _tudo()).get(str(guild_id), [])


async def get_por_nome(guild_id: int, nome: str):
    lista = await listar(guild_id)
    return next((g for g in lista if g["nome"].lower() == nome.lower()), None)


async def get_gangue_do_membro(guild_id: int, user_id: int):
    lista = await listar(guild_id)
    return next((g for g in lista if user_id in g["membros"]), None)


async def criar(guild_id: int, nome: str, lider_id: int) -> dict:
    lista = await listar(guild_id)
    gangue = {
        "id": str(uuid.uuid4())[:8],
        "nome": nome,
        "lider_id": lider_id,
        "membros": [lider_id],
        "emblema_url": None,
        "criado_em": time.time(),
    }
    lista.append(gangue)
    await _salvar_guild(guild_id, lista)
    return gangue


async def adicionar_membro(guild_id: int, gangue_id: str, user_id: int) -> bool:
    lista = await listar(guild_id)
    alvo = next((g for g in lista if g["id"] == gangue_id), None)
    if not alvo or user_id in alvo["membros"]:
        return False
    alvo["membros"].append(user_id)
    await _salvar_guild(guild_id, lista)
    return True


async def remover_membro(guild_id: int, gangue_id: str, user_id: int) -> bool:
    lista = await listar(guild_id)
    alvo = next((g for g in lista if g["id"] == gangue_id), None)
    if not alvo or user_id not in alvo["membros"]:
        return False
    alvo["membros"].remove(user_id)
    await _salvar_guild(guild_id, lista)
    return True


async def definir_emblema(guild_id: int, gangue_id: str, url: str) -> bool:
    lista = await listar(guild_id)
    alvo = next((g for g in lista if g["id"] == gangue_id), None)
    if not alvo:
        return False
    alvo["emblema_url"] = url
    await _salvar_guild(guild_id, lista)
    return True


async def transferir_lideranca(guild_id: int, gangue_id: str, novo_lider_id: int) -> bool:
    lista = await listar(guild_id)
    alvo = next((g for g in lista if g["id"] == gangue_id), None)
    if not alvo or novo_lider_id not in alvo["membros"]:
        return False
    alvo["lider_id"] = novo_lider_id
    await _salvar_guild(guild_id, lista)
    return True


async def dissolver(guild_id: int, gangue_id: str) -> bool:
    lista = await listar(guild_id)
    nova_lista = [g for g in lista if g["id"] != gangue_id]
    if len(nova_lista) == len(lista):
        return False
    await _salvar_guild(guild_id, nova_lista)
    return True