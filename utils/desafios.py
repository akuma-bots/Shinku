import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_DESAFIOS = "desafios.json"
ARQUIVO_COMPETITIVO = "competitivo.json"


async def _tudo():
    return await carregar(
        ARQUIVO_DESAFIOS,
        {},
    )


async def _salvar_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo()

    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_DESAFIOS,
        dados,
    )


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
        "id": str(
            uuid.uuid4()
        )[:8],

        "guild_id": guild_id,

        "desafiante_id": (
            desafiante_id
        ),

        "desafiado_id": (
            desafiado_id
        ),

        "status": "pendente",

        "vencedor_id": None,

        "perdedor_id": None,

        "aposta_xp": aposta_xp,

        "timestamp": time.time(),

        "mensagem_id": None,

        "canal_id": None,
    }

    lista.append(
        desafio
    )

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
            if d["id"] == desafio_id
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

    for desafio in lista:

        if desafio["id"] != desafio_id:
            continue

        desafio["canal_id"] = (
            canal_id
        )

        desafio["mensagem_id"] = (
            mensagem_id
        )

        break

    await _salvar_guild(
        guild_id,
        lista,
    )


async def definir_status(
    guild_id: int,
    desafio_id: str,
    status: str,
) -> dict:

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
            if d["id"] == desafio_id
        ),
        None,
    )

    if alvo:

        alvo["status"] = (
            status
        )

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
) -> dict:

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
            if d["id"] == desafio_id
        ),
        None,
    )

    if alvo:

        alvo["vencedor_id"] = (
            vencedor_id
        )

        alvo["perdedor_id"] = (
            perdedor_id
        )

        alvo["status"] = (
            "aguardando_revisao"
        )

        await _salvar_guild(
            guild_id,
            lista,
        )

        await _sincronizar_desafio_site(
            desafio=alvo,
        )

    return alvo


async def _sincronizar_desafio_site(
    desafio: dict,
):
    """
    Mantém uma representação do desafio
    dentro do competitivo.json para o Dashboard.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        {
            "catalogo": [],
            "perfis": {},
            "desafios": [],
        },
    )

    dados.setdefault(
        "catalogo",
        [],
    )

    dados.setdefault(
        "perfis",
        {},
    )

    dados.setdefault(
        "desafios",
        [],
    )

    desafio_id = desafio.get(
        "id"
    )

    existentes = [
        item
        for item in dados["desafios"]
        if item.get("id") != desafio_id
    ]

    existentes.append(
        {
            "id": desafio_id,
            "guildId": str(
                desafio.get(
                    "guild_id",
                    "",
                )
            ),
            "desafianteId": str(
                desafio.get(
                    "desafiante_id",
                    "",
                )
            ),
            "desafiadoId": str(
                desafio.get(
                    "desafiado_id",
                    "",
                )
            ),
            "status": desafio.get(
                "status",
                "pendente",
            ),
            "vencedorId": (
                str(
                    desafio["vencedor_id"]
                )
                if desafio.get(
                    "vencedor_id"
                )
                else None
            ),
            "perdedorId": (
                str(
                    desafio["perdedor_id"]
                )
                if desafio.get(
                    "perdedor_id"
                )
                else None
            ),
            "apostaXp": int(
                desafio.get(
                    "aposta_xp",
                    0,
                )
                or 0
            ),
            "timestamp": desafio.get(
                "timestamp"
            ),
            "canalId": (
                str(
                    desafio["canal_id"]
                )
                if desafio.get(
                    "canal_id"
                )
                else None
            ),
            "mensagemId": (
                str(
                    desafio["mensagem_id"]
                )
                if desafio.get(
                    "mensagem_id"
                )
                else None
            ),
        }
    )

    dados["desafios"] = existentes

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )


async def sincronizar_todos_site(
    guild_id: int,
) -> int:
    """
    Migra todos os desafios existentes da guild
    para o competitivo.json compartilhado.
    """

    lista = (
        await _tudo()
    ).get(
        str(guild_id),
        [],
    )

    quantidade = 0

    for desafio in lista:

        if not isinstance(
            desafio,
            dict,
        ):
            continue

        try:

            desafio.setdefault(
                "guild_id",
                guild_id,
            )

            await _sincronizar_desafio_site(
                desafio
            )

            quantidade += 1

        except Exception as erro:

            print(
                "[DESAFIOS] "
                f"Falha ao sincronizar "
                f"{desafio.get('id')}: "
                f"{erro}"
            )

    return quantidade


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
            desafio["desafiante_id"],
            desafio["desafiado_id"],
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
        desafio["timestamp"],
    )