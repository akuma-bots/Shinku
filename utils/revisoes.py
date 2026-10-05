import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_REVISOES = "revisoes.json"


async def _tudo():
    return await carregar(
        ARQUIVO_REVISOES,
        {},
    )


async def _salvar_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo()
    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_REVISOES,
        dados,
    )


async def listar(
    guild_id: int,
    status: str = None,
) -> list:

    dados = await _tudo()

    lista = dados.get(
        str(guild_id),
        [],
    )

    if status:
        lista = [
            revisao
            for revisao in lista
            if revisao.get("status") == status
        ]

    return lista


async def criar_pendencia(
    guild_id: int,
    tipo: str,
    autor_id: int,
    referencia_id: str,
    print_url: str,
    titulo: str,
    descricao: str = None,
) -> dict:

    lista = await listar(guild_id)

    revisao = {
        "id": str(uuid.uuid4())[:8],
        "guild_id": guild_id,
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
        "criado_em": time.time(),
        "atualizado_em": time.time(),
    }

    lista.append(revisao)

    await _salvar_guild(
        guild_id,
        lista,
    )

    return revisao


async def get(
    guild_id: int,
    revisao_id: str,
):
    lista = await listar(guild_id)

    return next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )


async def definir_mensagem(
    guild_id: int,
    revisao_id: str,
    canal_id: int,
    mensagem_id: int,
):

    lista = await listar(guild_id)

    alvo = next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )

    if not alvo:
        return None

    alvo["canal_id"] = canal_id
    alvo["mensagem_id"] = mensagem_id
    alvo["atualizado_em"] = time.time()

    await _salvar_guild(
        guild_id,
        lista,
    )

    return alvo


async def definir_hash(
    guild_id: int,
    revisao_id: str,
    hash_imagem: str,
):

    lista = await listar(guild_id)

    alvo = next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )

    if not alvo:
        return None

    alvo["hash_imagem"] = hash_imagem
    alvo["atualizado_em"] = time.time()

    await _salvar_guild(
        guild_id,
        lista,
    )

    return alvo


async def buscar_por_hash(
    guild_id: int,
    hash_imagem: str,
    excluir_id: str = None,
) -> list:

    lista = await listar(guild_id)

    return [
        revisao
        for revisao in lista
        if (
            revisao.get("hash_imagem")
            == hash_imagem
            and revisao.get("id") != excluir_id
            and revisao.get("status") != "rejeitada"
        )
    ]


async def aprovar(
    guild_id: int,
    revisao_id: str,
    revisor_id: int,
):

    lista = await listar(guild_id)

    alvo = next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )

    if not alvo:
        return None

    if alvo.get("status") != "pendente":
        return None

    alvo["status"] = "aprovada"
    alvo["revisor_id"] = revisor_id
    alvo["aprovado_em"] = time.time()
    alvo["atualizado_em"] = time.time()

    await _salvar_guild(
        guild_id,
        lista,
    )

    return alvo


async def rejeitar(
    guild_id: int,
    revisao_id: str,
    revisor_id: int,
    motivo: str = None,
):

    lista = await listar(guild_id)

    alvo = next(
        (
            revisao
            for revisao in lista
            if revisao.get("id") == revisao_id
        ),
        None,
    )

    if not alvo:
        return None

    if alvo.get("status") != "pendente":
        return None

    alvo["status"] = "rejeitada"
    alvo["revisor_id"] = revisor_id
    alvo["motivo_rejeicao"] = motivo
    alvo["rejeitada_em"] = time.time()
    alvo["atualizado_em"] = time.time()

    await _salvar_guild(
        guild_id,
        lista,
    )

    return alvo


async def sincronizar_todos_site(
    guild_id: int,
) -> int:

    lista = await listar(guild_id)

    quantidade = 0

    for revisao in lista:

        if not isinstance(revisao, dict):
            continue

        revisao.setdefault(
            "guild_id",
            guild_id,
        )

        revisao.setdefault(
            "atualizado_em",
            time.time(),
        )

        quantidade += 1

    await _salvar_guild(
        guild_id,
        lista,
    )

    return quantidade