import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_MISSOES = "missoes.json"  # { guild_id: [ {missao...}, ... ] }


async def _tudo():
    return await carregar(ARQUIVO_MISSOES, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_MISSOES, dados)


async def listar(guild_id: int, tipo: str = None, origem: str = None, apenas_ativas: bool = True) -> list:
    dados = await _tudo()
    lista = dados.get(str(guild_id), [])
    if tipo:
        lista = [m for m in lista if m["tipo"] == tipo]
    if origem:
        lista = [m for m in lista if m.get("origem", "lider") == origem]
    if apenas_ativas:
        lista = [m for m in lista if m["ativa"]]
    return lista


async def criar(guild_id: int, tipo: str, titulo: str, descricao: str,
                 recompensa_xp: int, criado_por: int = None, origem: str = "lider") -> dict:
    lista_completa = (await _tudo()).get(str(guild_id), [])
    missao = {
        "id": str(uuid.uuid4())[:8],
        "tipo": tipo,
        "titulo": titulo,
        "descricao": descricao,
        "recompensa_xp": recompensa_xp,
        "criado_por": criado_por,
        "origem": origem,  # "lider" ou "npc"
        "ativa": True,
        "timestamp": time.time(),
    }
    lista_completa.append(missao)
    await _salvar_guild(guild_id, lista_completa)
    return missao


async def get(guild_id: int, missao_id: str):
    lista = (await _tudo()).get(str(guild_id), [])
    return next((m for m in lista if m["id"] == missao_id), None)


async def desativar(guild_id: int, missao_id: str) -> bool:
    lista = (await _tudo()).get(str(guild_id), [])
    alvo = next((m for m in lista if m["id"] == missao_id), None)
    if not alvo:
        return False
    alvo["ativa"] = False
    await _salvar_guild(guild_id, lista)
    return True


async def desativar_todas_por_origem(guild_id: int, origem: str):
    """Usado pelo reset diário: desativa todas as missões NPC do dia anterior
    antes de gerar as novas, sem mexer nas missões criadas por líderes."""
    lista = (await _tudo()).get(str(guild_id), [])
    for m in lista:
        if m.get("origem", "lider") == origem and m["ativa"]:
            m["ativa"] = False
    await _salvar_guild(guild_id, lista)