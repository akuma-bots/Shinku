import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO = "punicoes.json"  # { guild_id: [ {id, membro_id, tipo, motivo, aplicado_por_id, timestamp} ] }


async def registrar_punicao(guild_id: int, membro_id: int, tipo: str, motivo: str, aplicado_por_id: int = None):
    """tipo: 'ban' | 'kick' | 'mute' | 'warn' | 'aviso_automatico'"""
    todos = await carregar(ARQUIVO, {})
    lista = todos.setdefault(str(guild_id), [])
    lista.append({
        "id": str(uuid.uuid4())[:8],
        "membro_id": membro_id,
        "tipo": tipo,
        "motivo": motivo,
        "aplicado_por_id": aplicado_por_id,  # None = automático (automod)
        "timestamp": time.time(),
    })
    await salvar(ARQUIVO, todos)


async def historico_punicoes(guild_id: int, membro_id: int = None, limite: int = 15) -> list:
    todos = await carregar(ARQUIVO, {})
    lista = todos.get(str(guild_id), [])
    if membro_id is not None:
        lista = [p for p in lista if p["membro_id"] == membro_id]
    return sorted(lista, key=lambda p: p["timestamp"], reverse=True)[:limite]
