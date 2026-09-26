import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_DESAFIOS = "desafios.json"  # { guild_id: [ {desafio...}, ... ] }


async def _tudo():
    return await carregar(ARQUIVO_DESAFIOS, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_DESAFIOS, dados)


async def criar(guild_id: int, desafiante_id: int, desafiado_id: int, aposta_xp: int = 0) -> dict:
    lista = (await _tudo()).get(str(guild_id), [])
    desafio = {
        "id": str(uuid.uuid4())[:8],
        "desafiante_id": desafiante_id,
        "desafiado_id": desafiado_id,
        "status": "pendente",
        "vencedor_id": None,
        "perdedor_id": None,
        "aposta_xp": aposta_xp,
        "timestamp": time.time(),
        "mensagem_id": None,
        "canal_id": None,
    }
    lista.append(desafio)
    await _salvar_guild(guild_id, lista)
    return desafio


async def get(guild_id: int, desafio_id: str):
    lista = (await _tudo()).get(str(guild_id), [])
    return next((d for d in lista if d["id"] == desafio_id), None)


async def definir_mensagem(guild_id: int, desafio_id: str, canal_id: int, mensagem_id: int):
    lista = (await _tudo()).get(str(guild_id), [])
    for d in lista:
        if d["id"] == desafio_id:
            d["canal_id"] = canal_id
            d["mensagem_id"] = mensagem_id
    await _salvar_guild(guild_id, lista)


async def definir_status(guild_id: int, desafio_id: str, status: str) -> dict:
    lista = (await _tudo()).get(str(guild_id), [])
    alvo = next((d for d in lista if d["id"] == desafio_id), None)
    if alvo:
        alvo["status"] = status
        await _salvar_guild(guild_id, lista)
    return alvo


async def definir_resultado(guild_id: int, desafio_id: str, vencedor_id: int, perdedor_id: int) -> dict:
    lista = (await _tudo()).get(str(guild_id), [])
    alvo = next((d for d in lista if d["id"] == desafio_id), None)
    if alvo:
        alvo["vencedor_id"] = vencedor_id
        alvo["perdedor_id"] = perdedor_id
        alvo["status"] = "aguardando_revisao"
        await _salvar_guild(guild_id, lista)
    return alvo


async def get_ultimo_entre(guild_id: int, id_a: int, id_b: int):
    lista = (await _tudo()).get(str(guild_id), [])
    relacionados = [d for d in lista if {d["desafiante_id"], d["desafiado_id"]} == {id_a, id_b}]
    if not relacionados:
        return None
    return max(relacionados, key=lambda d: d["timestamp"])