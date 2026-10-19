import asyncio
import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO = "punicoes.json"
_PUNICOES_LOCK = asyncio.Lock()


async def _tudo():
    dados = await carregar(ARQUIVO, {})
    return dados if isinstance(dados, dict) else {}


def _lista_valida(valor):
    if not isinstance(valor, list):
        return []
    return [registro for registro in valor if isinstance(registro, dict)]


async def registrar_punicao(
    guild_id: int,
    membro_id: int,
    tipo: str,
    motivo: str,
    aplicado_por_id: int = None,
):
    """Registra uma punição sem perder eventos concorrentes no mesmo processo."""
    tipo = str(tipo or "").strip().lower()
    if not tipo:
        raise ValueError("O tipo da punição não pode ficar vazio.")
    motivo = str(motivo or "").strip()
    if not motivo:
        motivo = "Sem motivo informado."

    async with _PUNICOES_LOCK:
        todos = await _tudo()
        lista = _lista_valida(todos.get(str(guild_id), []))
        punicao = {
            "id": uuid.uuid4().hex[:8],
            "guild_id": int(guild_id),
            "membro_id": int(membro_id),
            "tipo": tipo,
            "motivo": motivo[:2000],
            "aplicado_por_id": int(aplicado_por_id) if aplicado_por_id is not None else None,
            "timestamp": time.time(),
        }
        lista.append(punicao)
        todos[str(guild_id)] = lista
        await salvar(ARQUIVO, todos)
        return punicao


async def historico_punicoes(
    guild_id: int,
    membro_id: int = None,
    limite: int = 15,
) -> list:
    todos = await _tudo()
    lista = _lista_valida(todos.get(str(guild_id), []))
    if membro_id is not None:
        try:
            membro_id = int(membro_id)
        except (TypeError, ValueError, OverflowError):
            return []
        filtradas = []
        for punicao in lista:
            try:
                id_registro = int(punicao.get("membro_id"))
            except (TypeError, ValueError, OverflowError):
                continue
            if id_registro == membro_id:
                filtradas.append(punicao)
        lista = filtradas

    def timestamp(registro):
        try:
            return float(registro.get("timestamp", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return 0.0

    try:
        limite = max(0, min(100, int(limite)))
    except (TypeError, ValueError, OverflowError):
        limite = 15
    return sorted(lista, key=timestamp, reverse=True)[:limite]


async def obter_todas_punicoes(guild_id: int) -> list:
    """Retorna o histórico válido para uso interno do bot."""
    todos = await _tudo()
    return _lista_valida(todos.get(str(guild_id), []))


async def remover_punicao(guild_id: int, punicao_id: str) -> bool:
    async with _PUNICOES_LOCK:
        todos = await _tudo()
        lista = _lista_valida(todos.get(str(guild_id), []))
        nova_lista = [punicao for punicao in lista if str(punicao.get("id")) != str(punicao_id)]
        if len(nova_lista) == len(lista):
            return False
        todos[str(guild_id)] = nova_lista
        await salvar(ARQUIVO, todos)
        return True
