import asyncio
import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_DESAFIOS = "desafios.json"
_DESAFIOS_TRANSICAO_LOCK = asyncio.Lock()


async def _tudo():
    return await carregar(ARQUIVO_DESAFIOS, {})


async def _salvar_guild(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_DESAFIOS, dados)



async def criar(
    guild_id: int,
    desafiante_id: int,
    desafiado_id: int,
    aposta_xp: int = 0,
) -> dict:

    lista = (
        await _tudo()
    ).get(
        str(guild_id),
        [],
    )

    desafio = {
        "id": str(uuid.uuid4())[:8],
        "guild_id": guild_id,
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

    await _salvar_guild(
        guild_id,
        lista,
    )


    return desafio


async def get(
    guild_id: int,
    desafio_id: str,
):
    lista = (
        await _tudo()
    ).get(
        str(guild_id),
        [],
    )

    return next(
        (
            d
            for d in lista
            if d.get("id") == desafio_id
        ),
        None,
    )


async def definir_mensagem(
    guild_id: int,
    desafio_id: str,
    canal_id: int,
    mensagem_id: int,
):
    lista = (
        await _tudo()
    ).get(
        str(guild_id),
        [],
    )

    alvo = next(
        (
            d
            for d in lista
            if d.get("id") == desafio_id
        ),
        None,
    )

    if not alvo:
        return None

    alvo["canal_id"] = canal_id
    alvo["mensagem_id"] = mensagem_id

    await _salvar_guild(
        guild_id,
        lista,
    )


    return alvo


async def transicionar_status(
    guild_id: int,
    desafio_id: str,
    status_esperado: str,
    status_novo: str,
):
    """Altera o estado somente se ele ainda corresponder ao esperado.

    A verificação e a gravação compartilham o mesmo lock para impedir que
    dois cliques concorrentes aceitem/recusem o mesmo desafio.
    """
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = (await _tudo()).get(str(guild_id), [])
        alvo = next(
            (d for d in lista if d.get("id") == desafio_id),
            None,
        )
        if not alvo or alvo.get("status") != status_esperado:
            return None

        alvo["status"] = status_novo
        await _salvar_guild(guild_id, lista)
        return alvo
        return alvo


async def definir_status(
    guild_id: int,
    desafio_id: str,
    status: str,
):
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = (
            await _tudo()
        ).get(
            str(guild_id),
            [],
        )

        alvo = next(
            (
                d
                for d in lista
                if d.get("id") == desafio_id
            ),
            None,
        )

        if not alvo:
            return None

        alvo["status"] = status

        await _salvar_guild(
            guild_id,
            lista,
        )


        return alvo


async def definir_resultado(
    guild_id: int,
    desafio_id: str,
    vencedor_id: int,
    perdedor_id: int,
):
    async with _DESAFIOS_TRANSICAO_LOCK:
        lista = (
            await _tudo()
        ).get(
            str(guild_id),
            [],
        )

        alvo = next(
            (
                d
                for d in lista
                if d.get("id") == desafio_id
            ),
            None,
        )

        if not alvo:
            return None
        if alvo.get("status") != "aceito":
            return None

        alvo["vencedor_id"] = vencedor_id
        alvo["perdedor_id"] = perdedor_id
        alvo["status"] = "aguardando_revisao"

        await _salvar_guild(
            guild_id,
            lista,
        )

        return alvo
        return alvo



async def get_ultimo_entre(
    guild_id: int,
    id_a: int,
    id_b: int,
):
    lista = (
        await _tudo()
    ).get(
        str(guild_id),
        [],
    )

    relacionados = [
        desafio
        for desafio in lista
        if {
            desafio.get("desafiante_id"),
            desafio.get("desafiado_id"),
        }
        == {
            id_a,
            id_b,
        }
    ]

    if not relacionados:
        return None

    return max(
        relacionados,
        key=lambda desafio:
        desafio.get("timestamp", 0),
    )