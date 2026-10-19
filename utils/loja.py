import asyncio
import uuid

from utils.storage import carregar, salvar

ARQUIVO_LOJA = "loja.json"  # { guild_id: [ {item...}, ... ] }
_LOJA_LOCK = asyncio.Lock()


async def _tudo():
    dados = await carregar(ARQUIVO_LOJA, {})
    return dados if isinstance(dados, dict) else {}


def _normalizar_item(item):
    if not isinstance(item, dict):
        return None
    item_id = str(item.get("id") or "").strip()
    nome = str(item.get("nome") or "").strip()
    if not item_id or not nome:
        return None
    try:
        preco = int(item.get("preco_xp", 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if preco < 0:
        return None
    descricao = str(item.get("descricao") or "")
    cargo_id = item.get("cargo_id")
    try:
        cargo_id = int(cargo_id) if cargo_id not in (None, "") else None
    except (TypeError, ValueError, OverflowError):
        cargo_id = None
    return {**item, "id": item_id, "nome": nome, "descricao": descricao,
            "preco_xp": preco, "cargo_id": cargo_id}


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_LOJA, dados)


async def listar(guild_id: int) -> list:
    dados = await _tudo()
    lista = dados.get(str(guild_id), [])
    if not isinstance(lista, list):
        return []
    return [item for raw in lista if (item := _normalizar_item(raw)) is not None]


async def get(guild_id: int, item_id: str):
    item_id = str(item_id or "").strip()
    lista = await listar(guild_id)
    return next((item for item in lista if item["id"] == item_id), None)


async def adicionar(guild_id: int, nome: str, descricao: str, preco_xp: int, cargo_id: int = None) -> dict:
    nome = str(nome or "").strip()
    descricao = str(descricao or "").strip()
    if not nome:
        raise ValueError("O nome do item não pode ficar vazio.")
    try:
        preco_xp = int(preco_xp)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("O preço precisa ser um número inteiro válido.") from erro
    if preco_xp < 0:
        raise ValueError("O preço em XP não pode ser negativo.")
    if cargo_id is not None:
        try:
            cargo_id = int(cargo_id)
        except (TypeError, ValueError, OverflowError) as erro:
            raise ValueError("O ID do cargo é inválido.") from erro

    async with _LOJA_LOCK:
        lista = await listar(guild_id)
        item = {
            "id": uuid.uuid4().hex[:8],
            "nome": nome,
            "descricao": descricao,
            "preco_xp": preco_xp,
            "cargo_id": cargo_id,
        }
        lista.append(item)
        await _salvar_guild(guild_id, lista)
        return item


async def remover(guild_id: int, item_id: str) -> bool:
    async with _LOJA_LOCK:
        lista = await listar(guild_id)
        nova_lista = [item for item in lista if item["id"] != str(item_id)]
        if len(nova_lista) == len(lista):
            return False
        await _salvar_guild(guild_id, nova_lista)
        return True
