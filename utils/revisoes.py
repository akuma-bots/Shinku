import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_REVISOES = "revisoes.json"  # { guild_id: [ {revisao...}, ... ] }


async def _tudo():
    return await carregar(ARQUIVO_REVISOES, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_REVISOES, dados)


async def listar(guild_id: int, status: str = None) -> list:
    dados = await _tudo()
    lista = dados.get(str(guild_id), [])
    if status:
        lista = [r for r in lista if r["status"] == status]
    return lista


async def criar_pendencia(guild_id: int, tipo: str, autor_id: int, referencia_id: str,
                           print_url: str, titulo: str, descricao: str = None) -> dict:
    """tipo: 'missao', 'pvp' ou 'pve'. referencia_id: id da missão/luta relacionada
    (usado pelo processador de aprovação pra saber o que atualizar)."""
    lista = await listar(guild_id)
    revisao = {
        "id": str(uuid.uuid4())[:8],
        "tipo": tipo,
        "autor_id": autor_id,
        "referencia_id": referencia_id,
        "print_url": print_url,
        "titulo": titulo,
        "descricao": descricao,
        "status": "pendente",
        "revisor_id": None,
        "motivo_rejeicao": None,
        "timestamp": time.time(),
        "mensagem_id": None,
        "canal_id": None,
        "hash_imagem": None,
    }
    lista.append(revisao)
    await _salvar_guild(guild_id, lista)
    return revisao


async def get(guild_id: int, revisao_id: str):
    lista = await listar(guild_id)
    return next((r for r in lista if r["id"] == revisao_id), None)


async def definir_mensagem(guild_id: int, revisao_id: str, canal_id: int, mensagem_id: int):
    lista = await listar(guild_id)
    for r in lista:
        if r["id"] == revisao_id:
            r["canal_id"] = canal_id
            r["mensagem_id"] = mensagem_id
    await _salvar_guild(guild_id, lista)


async def definir_hash(guild_id: int, revisao_id: str, hash_imagem: str):
    lista = await listar(guild_id)
    for r in lista:
        if r["id"] == revisao_id:
            r["hash_imagem"] = hash_imagem
    await _salvar_guild(guild_id, lista)


async def buscar_por_hash(guild_id: int, hash_imagem: str, excluir_id: str = None) -> list:
    """Outras revisões (não rejeitadas) que usaram exatamente a mesma
    imagem — sinal de que a print pode estar sendo reaproveitada."""
    lista = await listar(guild_id)
    return [r for r in lista if r.get("hash_imagem") == hash_imagem and r["id"] != excluir_id and r["status"] != "rejeitada"]


async def aprovar(guild_id: int, revisao_id: str, revisor_id: int):
    lista = await listar(guild_id)
    alvo = next((r for r in lista if r["id"] == revisao_id), None)
    if not alvo or alvo["status"] != "pendente":
        return None
    alvo["status"] = "aprovada"
    alvo["revisor_id"] = revisor_id
    await _salvar_guild(guild_id, lista)
    return alvo


async def rejeitar(guild_id: int, revisao_id: str, revisor_id: int, motivo: str = None):
    lista = await listar(guild_id)
    alvo = next((r for r in lista if r["id"] == revisao_id), None)
    if not alvo or alvo["status"] != "pendente":
        return None
    alvo["status"] = "rejeitada"
    alvo["revisor_id"] = revisor_id
    alvo["motivo_rejeicao"] = motivo
    await _salvar_guild(guild_id, lista)
    return alvo