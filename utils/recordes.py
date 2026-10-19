import asyncio
import math

from utils.storage import carregar, salvar


ARQUIVO_RECORDES = "recordes.json"
_RECORDE_LOCK = asyncio.Lock()


async def _tudo():
    dados = await carregar(ARQUIVO_RECORDES, {})
    return dados if isinstance(dados, dict) else {}


async def obter_todos(guild_id: int) -> dict:
    dados = await _tudo()
    recordes = dados.get(str(guild_id), {})
    if not isinstance(recordes, dict):
        return {}
    return {
        str(categoria): registro
        for categoria, registro in recordes.items()
        if isinstance(registro, dict)
    }


async def verificar_e_atualizar(
    guild_id: int,
    categoria: str,
    user_id: int,
    valor: float,
):
    """Atualiza um recorde apenas com valores finitos e sem perder updates concorrentes."""
    categoria = str(categoria or "").strip()
    if not categoria:
        raise ValueError("A categoria do recorde não pode ficar vazia.")
    try:
        valor = float(valor)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("O valor do recorde precisa ser numérico.") from erro
    if not math.isfinite(valor) or valor < 0:
        raise ValueError("O valor do recorde precisa ser finito e não negativo.")

    async with _RECORDE_LOCK:
        dados = await _tudo()
        recordes_guild = dados.get(str(guild_id))
        if not isinstance(recordes_guild, dict):
            recordes_guild = {}
            dados[str(guild_id)] = recordes_guild

        atual = recordes_guild.get(categoria)
        if isinstance(atual, dict):
            try:
                valor_atual = float(atual.get("valor", 0))
            except (TypeError, ValueError, OverflowError):
                valor_atual = -1
            if math.isfinite(valor_atual) and valor <= valor_atual:
                return None

        novo = {"user_id": int(user_id), "valor": valor}
        recordes_guild[categoria] = novo
        await salvar(ARQUIVO_RECORDES, dados)
        return novo
