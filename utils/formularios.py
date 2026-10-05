import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_FORMULARIOS = "formularios.json"
ARQUIVO_RESPOSTAS = "formularios_respostas.json"


async def _tudo_formularios():
    return await carregar(
        ARQUIVO_FORMULARIOS,
        {},
    )


async def _salvar_formularios_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo_formularios()

    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_FORMULARIOS,
        dados,
    )


async def listar_formularios(
    guild_id: int,
) -> list:

    dados = await _tudo_formularios()

    return dados.get(
        str(guild_id),
        [],
    )


async def get_formulario(
    guild_id: int,
    formulario_id: str,
):
    lista = await listar_formularios(
        guild_id
    )

    return next(
        (
            formulario
            for formulario in lista
            if formulario.get("id") == formulario_id
        ),
        None,
    )


async def criar_formulario(
    guild_id: int,
    nome: str,
    titulo_painel: str,
    descricao_painel: str,
    banner_url: str,
    criado_por: int,
) -> dict:

    lista = await listar_formularios(
        guild_id
    )

    agora = time.time()

    formulario = {
        "id": str(uuid.uuid4())[:8],
        "guild_id": guild_id,
        "nome": nome,
        "titulo_painel": titulo_painel,
        "descricao_painel": descricao_painel,
        "banner_url": banner_url,
        "paginas": [],
        "cargos_notificar": [],
        "criado_por": criado_por,
        "timestamp": agora,
        "criado_em": agora,
        "atualizado_em": agora,
    }

    lista.append(formulario)

    await _salvar_formularios_guild(
        guild_id,
        lista,
    )

    return formulario


async def remover_formulario(
    guild_id: int,
    formulario_id: str,
) -> bool:

    lista = await listar_formularios(
        guild_id
    )

    nova_lista = [
        formulario
        for formulario in lista
        if formulario.get("id") != formulario_id
    ]

    if len(nova_lista) == len(lista):
        return False

    await _salvar_formularios_guild(
        guild_id,
        nova_lista,
    )

    return True


def perguntas_flat(
    formulario: dict,
) -> list:

    achatado = []

    for pagina in formulario.get(
        "paginas",
        [],
    ):
        achatado.extend(
            pagina
        )

    return achatado


async def adicionar_pagina(
    guild_id: int,
    formulario_id: str,
    perguntas: list,
) -> dict:

    lista = await listar_formularios(
        guild_id
    )

    alvo = next(
        (
            formulario
            for formulario in lista
            if formulario.get("id") == formulario_id
        ),
        None,
    )

    if not alvo:
        return None

    alvo.setdefault(
        "paginas",
        [],
    )

    alvo["paginas"].append(
        perguntas[:5]
    )

    alvo["atualizado_em"] = time.time()

    await _salvar_formularios_guild(
        guild_id,
        lista,
    )

    return alvo


async def remover_pagina(
    guild_id: int,
    formulario_id: str,
    indice: int,
) -> bool:

    lista = await listar_formularios(
        guild_id
    )

    alvo = next(
        (
            formulario
            for formulario in lista
            if formulario.get("id") == formulario_id
        ),
        None,
    )

    if not alvo:
        return False

    paginas = alvo.setdefault(
        "paginas",
        [],
    )

    if not (
        0 <= indice < len(paginas)
    ):
        return False

    paginas.pop(indice)

    alvo["atualizado_em"] = time.time()

    await _salvar_formularios_guild(
        guild_id,
        lista,
    )

    return True


async def adicionar_cargo_notificar(
    guild_id: int,
    formulario_id: str,
    cargo_id: int,
) -> bool:

    lista = await listar_formularios(
        guild_id
    )

    alvo = next(
        (
            formulario
            for formulario in lista
            if formulario.get("id") == formulario_id
        ),
        None,
    )

    if not alvo:
        return False

    cargos = alvo.setdefault(
        "cargos_notificar",
        [],
    )

    if cargo_id not in cargos:
        cargos.append(cargo_id)

    alvo["atualizado_em"] = time.time()

    await _salvar_formularios_guild(
        guild_id,
        lista,
    )

    return True


async def remover_cargo_notificar(
    guild_id: int,
    formulario_id: str,
    cargo_id: int,
) -> bool:

    lista = await listar_formularios(
        guild_id
    )

    alvo = next(
        (
            formulario
            for formulario in lista
            if formulario.get("id") == formulario_id
        ),
        None,
    )

    if not alvo:
        return False

    alvo["cargos_notificar"] = [
        cargo
        for cargo in alvo.get(
            "cargos_notificar",
            [],
        )
        if cargo != cargo_id
    ]

    alvo["atualizado_em"] = time.time()

    await _salvar_formularios_guild(
        guild_id,
        lista,
    )

    return True


# ============================================================
# RESPOSTAS
# ============================================================

async def _tudo_respostas():
    return await carregar(
        ARQUIVO_RESPOSTAS,
        {},
    )


async def _salvar_respostas_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo_respostas()

    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_RESPOSTAS,
        dados,
    )


async def criar_resposta(
    guild_id: int,
    formulario_id: str,
    autor_id: int,
    respostas: list,
) -> dict:

    dados = await _tudo_respostas()

    lista = dados.get(
        str(guild_id),
        [],
    )

    agora = time.time()

    resposta = {
        "id": str(uuid.uuid4())[:8],
        "guild_id": guild_id,
        "formulario_id": formulario_id,
        "autor_id": autor_id,
        "respostas": respostas,
        "status": "pendente",
        "revisor_id": None,
        "timestamp": agora,
        "criado_em": agora,
        "atualizado_em": agora,
    }

    lista.append(
        resposta
    )

    await _salvar_respostas_guild(
        guild_id,
        lista,
    )

    return resposta


async def get_resposta(
    guild_id: int,
    resposta_id: str,
):

    dados = await _tudo_respostas()

    lista = dados.get(
        str(guild_id),
        [],
    )

    return next(
        (
            resposta
            for resposta in lista
            if resposta.get("id") == resposta_id
        ),
        None,
    )


async def definir_status_resposta(
    guild_id: int,
    resposta_id: str,
    status: str,
    revisor_id: int,
):

    dados = await _tudo_respostas()

    lista = dados.get(
        str(guild_id),
        [],
    )

    alvo = next(
        (
            resposta
            for resposta in lista
            if resposta.get("id") == resposta_id
        ),
        None,
    )

    if not alvo:
        return None

    alvo["status"] = status
    alvo["revisor_id"] = revisor_id
    alvo["atualizado_em"] = time.time()

    await _salvar_respostas_guild(
        guild_id,
        lista,
    )

    return alvo


async def listar_respostas(
    guild_id: int,
    formulario_id: str = None,
    status: str = None,
) -> list:

    dados = await _tudo_respostas()

    lista = dados.get(
        str(guild_id),
        [],
    )

    if formulario_id:
        lista = [
            resposta
            for resposta in lista
            if resposta.get(
                "formulario_id"
            ) == formulario_id
        ]

    if status:
        lista = [
            resposta
            for resposta in lista
            if resposta.get("status") == status
        ]

    return lista


async def sincronizar_todos_site(
    guild_id: int,
) -> dict:

    formularios = await listar_formularios(
        guild_id
    )

    respostas = await listar_respostas(
        guild_id
    )

    agora = time.time()

    for formulario in formularios:
        formulario.setdefault(
            "guild_id",
            guild_id,
        )
        formulario.setdefault(
            "atualizado_em",
            agora,
        )

    for resposta in respostas:
        resposta.setdefault(
            "guild_id",
            guild_id,
        )
        resposta.setdefault(
            "atualizado_em",
            agora,
        )

    await _salvar_formularios_guild(
        guild_id,
        formularios,
    )

    await _salvar_respostas_guild(
        guild_id,
        respostas,
    )

    return {
        "formularios": len(
            formularios
        ),
        "respostas": len(
            respostas
        ),
    }