import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO = "punicoes.json"


async def _tudo():
    return await carregar(
        ARQUIVO,
        {},
    )


async def registrar_punicao(
    guild_id: int,
    membro_id: int,
    tipo: str,
    motivo: str,
    aplicado_por_id: int = None,
):
    """
    Registra uma punição no armazenamento compartilhado.

    Tipos aceitos:
    ban
    kick
    mute
    warn
    aviso_automatico
    """

    todos = await _tudo()

    lista = todos.setdefault(
        str(guild_id),
        [],
    )

    punicao = {
        "id": str(
            uuid.uuid4()
        )[:8],

        "guild_id": guild_id,

        "membro_id": membro_id,

        "tipo": tipo,

        "motivo": motivo,

        "aplicado_por_id": (
            aplicado_por_id
        ),

        "timestamp": time.time(),
    }

    lista.append(
        punicao
    )

    await salvar(
        ARQUIVO,
        todos,
    )

    return punicao


async def historico_punicoes(
    guild_id: int,
    membro_id: int = None,
    limite: int = 15,
) -> list:

    todos = await _tudo()

    lista = todos.get(
        str(guild_id),
        [],
    )

    if membro_id is not None:

        lista = [
            punicao
            for punicao in lista
            if punicao.get(
                "membro_id"
            ) == membro_id
        ]

    return sorted(
        lista,
        key=lambda punicao:
        punicao.get(
            "timestamp",
            0,
        ),
        reverse=True,
    )[:limite]


async def obter_todas_punicoes(
    guild_id: int,
) -> list:
    """
    Retorna todas as punições da guild
    para consumo do Dashboard.
    """

    todos = await _tudo()

    lista = todos.get(
        str(guild_id),
        [],
    )

    return list(lista)


async def remover_punicao(
    guild_id: int,
    punicao_id: str,
) -> bool:
    """
    Remove uma punição pelo ID.

    Retorna True quando encontrada e removida.
    """

    todos = await _tudo()

    lista = todos.get(
        str(guild_id),
        [],
    )

    nova_lista = [
        punicao
        for punicao in lista
        if punicao.get(
            "id"
        ) != punicao_id
    ]

    if len(nova_lista) == len(lista):
        return False

    todos[str(guild_id)] = (
        nova_lista
    )

    await salvar(
        ARQUIVO,
        todos,
    )

    return True


async def sincronizar_todos_site(
    guild_id: int,
) -> int:
    """
    Valida e normaliza todas as punições
    existentes para consumo do Dashboard.

    O Dashboard utiliza o mesmo punicoes.json,
    então nenhuma cópia separada é necessária.
    """

    todos = await _tudo()

    lista = todos.get(
        str(guild_id),
        [],
    )

    alterado = False

    for punicao in lista:

        if not isinstance(
            punicao,
            dict,
        ):
            continue

        if "guild_id" not in punicao:
            punicao["guild_id"] = (
                guild_id
            )
            alterado = True

        if "id" not in punicao:
            punicao["id"] = str(
                uuid.uuid4()
            )[:8]
            alterado = True

    if alterado:

        todos[str(guild_id)] = (
            lista
        )

        await salvar(
            ARQUIVO,
            todos,
        )

    return len(lista)