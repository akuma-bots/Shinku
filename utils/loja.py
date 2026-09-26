import uuid
from utils.storage import carregar, salvar

ARQUIVO_LOJA = "loja.json"  # { guild_id: [ {item...}, ... ] }


async def _tudo():
    return await carregar(ARQUIVO_LOJA, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_LOJA, dados)


async def listar(guild_id: int) -> list:
    return (await _tudo()).get(str(guild_id), [])


async def get(guild_id: int, item_id: str):
    lista = await listar(guild_id)
    return next((i for i in lista if i["id"] == item_id), None)


async def adicionar(guild_id: int, nome: str, descricao: str, preco_xp: int, cargo_id: int = None) -> dict:
    lista = await listar(guild_id)
    item = {"id": str(uuid.uuid4())[:8], "nome": nome, "descricao": descricao, "preco_xp": preco_xp, "cargo_id": cargo_id}
    lista.append(item)
    await _salvar_guild(guild_id, lista)
    return item


async def remover(guild_id: int, item_id: str) -> bool:
    lista = await listar(guild_id)
    nova_lista = [i for i in lista if i["id"] != item_id]
    if len(nova_lista) == len(lista):
        return False
    await _salvar_guild(guild_id, nova_lista)
    return True