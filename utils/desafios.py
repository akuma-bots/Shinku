import asyncio
import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_DESAFIOS = "desafios.json"
_DESAFIOS_TRANSICAO_LOCK = asyncio.Lock()


async def _tudo():
    dados = await carregar(ARQUIVO_DESAFIOS, {})
    return dados if isinstance(dados, dict) else {}


def _lista_valida(valor):
    if not isinstance(valor, list):
        return []
    return [desafio for desafio in valor if isinstance(desafio, dict)]


async def _lista_guild(guild_id: int) -> list:
    dados = await _tudo()
    return _lista_valida(dados.get(str(guild_id), []))


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = _lista_valida(lista)
    await salvar(ARQUIVO_DESAFIOS, dados)


async def criar(
    guild_id: int,
    desafiante_id: int,
    desafiado_id: int,
    aposta_xp: int = 0,
) -> dict:
    if int(desafiante_id) == int(desafiado_id):
        raise ValueError("Um membro não pode desafiar a si mesmo.")
    try:
        aposta_xp = int(aposta_xp or 0)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("A aposta precisa ser um número inteiro válido.") from erro
    if aposta_xp < 0:
        raise ValueError("A aposta não pode ser negativa.")

    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = await _lista_guild(guild_id)
        par = {int(desafiante_id), int(desafiado_id)}
        ativo = None
        for registro in lista:
            try:
                par_registro = {
                    int(registro.get("desafiante_id")),
                    int(registro.get("desafiado_id")),
                }
            except (TypeError, ValueError, OverflowError):
                continue
            if (
                par_registro == par
                and registro.get("status") in {
                    "pendente", "processando_aceite", "aceito", "aguardando_revisao",
                }
            ):
                ativo = registro
                break
        if ativo:
            raise ValueError("Já existe um desafio ativo entre esses membros.")

        desafio = {
            "id": uuid.uuid4().hex[:8],
            "guild_id": int(guild_id),
            "desafiante_id": int(desafiante_id),
            "desafiado_id": int(desafiado_id),
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
    lista = await _lista_guild(guild_id)
    return next((d for d in lista if str(d.get("id")) == str(desafio_id)), None)


async def definir_mensagem(guild_id: int, desafio_id: str, canal_id: int, mensagem_id: int):
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = await _lista_guild(guild_id)
        alvo = next((d for d in lista if str(d.get("id")) == str(desafio_id)), None)
        if not alvo:
            return None
        alvo["canal_id"] = int(canal_id)
        alvo["mensagem_id"] = int(mensagem_id)
        await _salvar_guild(guild_id, lista)
        return alvo


async def transicionar_status(
    guild_id: int,
    desafio_id: str,
    status_esperado: str,
    status_novo: str,
):
    """Muda o estado apenas se ele ainda corresponder ao esperado."""
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = await _lista_guild(guild_id)
        alvo = next((d for d in lista if str(d.get("id")) == str(desafio_id)), None)
        if not alvo or alvo.get("status") != status_esperado:
            return None
        alvo["status"] = status_novo
        await _salvar_guild(guild_id, lista)
        return alvo


async def definir_status(guild_id: int, desafio_id: str, status: str):
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = await _lista_guild(guild_id)
        alvo = next((d for d in lista if str(d.get("id")) == str(desafio_id)), None)
        if not alvo:
            return None
        alvo["status"] = status
        await _salvar_guild(guild_id, lista)
        return alvo


async def definir_resultado(
    guild_id: int,
    desafio_id: str,
    vencedor_id: int,
    perdedor_id: int,
):
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = await _lista_guild(guild_id)
        alvo = next((d for d in lista if str(d.get("id")) == str(desafio_id)), None)
        if not alvo or alvo.get("status") != "aceito":
            return None
        participantes = {int(alvo.get("desafiante_id", 0)), int(alvo.get("desafiado_id", 0))}
        if int(vencedor_id) not in participantes or int(perdedor_id) not in participantes:
            return None
        if int(vencedor_id) == int(perdedor_id):
            return None
        alvo["vencedor_id"] = int(vencedor_id)
        alvo["perdedor_id"] = int(perdedor_id)
        alvo["status"] = "aguardando_revisao"
        await _salvar_guild(guild_id, lista)
        return alvo


async def get_ultimo_entre(guild_id: int, id_a: int, id_b: int):
    lista = await _lista_guild(guild_id)
    relacionados = []
    par = {int(id_a), int(id_b)}
    for desafio in lista:
        try:
            jogadores = {
                int(desafio.get("desafiante_id")),
                int(desafio.get("desafiado_id")),
            }
            timestamp = float(desafio.get("timestamp", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if jogadores == par:
            relacionados.append((timestamp, desafio))
    if not relacionados:
        return None
    return max(relacionados, key=lambda item: item[0])[1]
