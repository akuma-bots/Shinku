import time
import uuid
import unicodedata

from utils.storage import carregar, salvar


ARQUIVO_TIPOS = "ticket_tipos.json"
ARQUIVO_TICKETS = "tickets.json"


TIPOS_PADRAO = [
    {
        "valor": "recrutamento",
        "label": "Recrutamento NÊMESIS",
        "emoji": "⚔️",
        "descricao": "Inscrição, entrada na gangue e avaliação de novos membros.",
        "usa_ia": False,
    },
    {
        "valor": "hierarquia_divisoes",
        "label": "Hierarquia e Divisões",
        "emoji": "◈",
        "descricao": "Cargos, liderança, equipes, divisões e responsabilidades.",
        "usa_ia": False,
    },
    {
        "valor": "conflitos_denuncias",
        "label": "Conflitos e Denúncias",
        "emoji": "⚖️",
        "descricao": "Relate problemas, condutas inadequadas ou conflitos internos.",
        "usa_ia": False,
    },
    {
        "valor": "guerras_desafios",
        "label": "Guerras e Desafios",
        "emoji": "⚔️",
        "descricao": "Organização de guerras, desafios, disputas e questões competitivas.",
        "usa_ia": False,
    },
    {
        "valor": "suporte_comunidade",
        "label": "Suporte da Comunidade",
        "emoji": "✦",
        "descricao": "Ajuda com o servidor, bot, site, acesso ou funcionamento dos sistemas.",
        "usa_ia": False,
    },
    {
        "valor": "aliancas",
        "label": "Alianças",
        "emoji": "◇",
        "descricao": "Propostas de aliança, cooperação entre grupos e assuntos diplomáticos da NÊMESIS.",
        "usa_ia": False,
    },
    {
        "valor": "eventos_atividades",
        "label": "Eventos e Atividades",
        "emoji": "✧",
        "descricao": "Eventos, atividades, torneios e iniciativas da NÊMESIS.",
        "usa_ia": False,
    },
    {
        "valor": "sugestoes_projetos",
        "label": "Sugestões e Projetos",
        "emoji": "▣",
        "descricao": "Envie sugestões, propostas de melhoria ou ideias para novos projetos.",
        "usa_ia": False,
    },
]


def _slug(
    texto: str,
) -> str:

    texto = texto.lower().strip()

    texto = "".join(
        c
        for c in unicodedata.normalize(
            "NFD",
            texto,
        )
        if unicodedata.category(c) != "Mn"
    )

    return "_".join(
        texto.split()
    )


async def _tudo():
    return await carregar(
        ARQUIVO_TIPOS,
        {},
    )


async def get_tipos(
    guild_id: int,
) -> list:

    dados = await _tudo()

    return (
        dados.get(
            str(guild_id)
        )
        or list(TIPOS_PADRAO)
    )


async def set_tipos(
    guild_id: int,
    lista: list,
):

    dados = await _tudo()

    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO_TIPOS,
        dados,
    )


async def adicionar_tipo(
    guild_id: int,
    label: str,
    descricao: str,
    emoji: str,
    usa_ia: bool,
) -> dict:

    tipos = await get_tipos(
        guild_id
    )

    tipo = {
        "valor": _slug(label),
        "label": label,
        "emoji": emoji,
        "descricao": descricao,
        "usa_ia": usa_ia,
    }

    tipos = [
        item
        for item in tipos
        if item["valor"] != tipo["valor"]
    ]

    tipos.append(
        tipo
    )

    await set_tipos(
        guild_id,
        tipos,
    )

    return tipo


async def remover_tipo(
    guild_id: int,
    valor: str,
) -> bool:

    tipos = await get_tipos(
        guild_id
    )

    nova_lista = [
        tipo
        for tipo in tipos
        if tipo["valor"] != valor
    ]

    if len(nova_lista) == len(tipos):
        return False

    await set_tipos(
        guild_id,
        nova_lista,
    )

    return True


def construir_topic(
    user_id: int,
    tipo: str,
) -> str:

    return (
        f"ticket-owner:{user_id}:tipo:{tipo}"
    )


def parse_topic(
    topic: str,
):

    if (
        not topic
        or not topic.startswith(
            "ticket-owner:"
        )
    ):
        return None

    resto = topic[
        len("ticket-owner:") :
    ]

    if ":tipo:" in resto:

        owner_id, tipo = (
            resto.split(
                ":tipo:",
                1,
            )
        )

    else:

        owner_id = resto
        tipo = "outro"

    return {
        "owner_id": owner_id,
        "tipo": tipo,
    }


# ==========================================================
# TICKETS
# ==========================================================


async def _tudo_tickets():
    return await carregar(
        ARQUIVO_TICKETS,
        {},
    )


async def _salvar_tickets(
    dados: dict,
):
    await salvar(
        ARQUIVO_TICKETS,
        dados,
    )


async def listar_tickets(
    guild_id: int,
    status: str = None,
) -> list:

    dados = await _tudo_tickets()

    lista = dados.get(
        str(guild_id),
        [],
    )

    if status:
        lista = [
            ticket
            for ticket in lista
            if ticket.get("status") == status
        ]

    return lista


async def get_ticket(
    guild_id: int,
    ticket_id: str,
):

    lista = await listar_tickets(
        guild_id
    )

    return next(
        (
            ticket
            for ticket in lista
            if ticket.get("id") == ticket_id
        ),
        None,
    )


async def get_ticket_por_canal(
    guild_id: int,
    canal_id: int,
):

    lista = await listar_tickets(
        guild_id
    )

    return next(
        (
            ticket
            for ticket in lista
            if str(
                ticket.get("canal_id")
            )
            == str(canal_id)
        ),
        None,
    )


async def get_ticket_aberto_usuario(
    guild_id: int,
    usuario_id: int,
):

    lista = await listar_tickets(
        guild_id,
        status="aberto",
    )

    return next(
        (
            ticket
            for ticket in lista
            if str(
                ticket.get("usuario_id")
            )
            == str(usuario_id)
        ),
        None,
    )


async def criar_ticket(
    guild_id: int,
    usuario_id: int,
    tipo: str,
    canal_id: int = None,
    mensagem_id: int = None,
) -> dict:

    dados = await _tudo_tickets()

    lista = dados.setdefault(
        str(guild_id),
        [],
    )

    ticket_existente = next(
        (
            ticket
            for ticket in lista
            if str(
                ticket.get("usuario_id")
            )
            == str(usuario_id)
            and ticket.get("status")
            == "aberto"
        ),
        None,
    )

    if ticket_existente:
        return ticket_existente

    ticket = {
        "id": str(
            uuid.uuid4()
        )[:8],
        "guild_id": guild_id,
        "usuario_id": usuario_id,
        "tipo": tipo,
        "canal_id": canal_id,
        "mensagem_id": mensagem_id,
        "status": "aberto",
        "criado_em": time.time(),
        "fechado_em": None,
        "fechado_por_id": None,
        "motivo_fechamento": None,
        "atendido_por_id": None,
    }

    lista.append(
        ticket
    )

    await _salvar_tickets(
        dados
    )

    return ticket


async def atualizar_ticket(
    guild_id: int,
    ticket_id: str,
    **campos,
):

    dados = await _tudo_tickets()

    lista = dados.get(
        str(guild_id),
        [],
    )

    alvo = next(
        (
            ticket
            for ticket in lista
            if ticket.get("id") == ticket_id
        ),
        None,
    )

    if not alvo:
        return None

    for chave, valor in campos.items():

        if valor is not None:
            alvo[chave] = valor

    await _salvar_tickets(
        dados
    )

    return alvo


async def fechar_ticket(
    guild_id: int,
    ticket_id: str,
    fechado_por_id: int = None,
    motivo: str = None,
):

    return await atualizar_ticket(
        guild_id,
        ticket_id,
        status="fechado",
        fechado_em=time.time(),
        fechado_por_id=fechado_por_id,
        motivo_fechamento=motivo,
    )


async def registrar_atendimento(
    guild_id: int,
    ticket_id: str,
    atendente_id: int,
):

    return await atualizar_ticket(
        guild_id,
        ticket_id,
        atendido_por_id=atendente_id,
    )


async def sincronizar_canal_ticket(
    guild_id: int,
    canal_id: int,
    mensagem_id: int = None,
    usuario_id: int = None,
    tipo: str = "outro",
):

    ticket = await get_ticket_por_canal(
        guild_id,
        canal_id,
    )

    if ticket:

        campos = {}

        if mensagem_id is not None:
            campos["mensagem_id"] = (
                mensagem_id
            )

        if usuario_id is not None:
            campos["usuario_id"] = (
                usuario_id
            )

        if tipo:
            campos["tipo"] = tipo

        return await atualizar_ticket(
            guild_id,
            ticket["id"],
            **campos,
        )

    return await criar_ticket(
        guild_id=guild_id,
        usuario_id=(
            usuario_id
            if usuario_id is not None
            else 0
        ),
        tipo=tipo,
        canal_id=canal_id,
        mensagem_id=mensagem_id,
    )


async def sincronizar_todos_site(
    guild_id: int,
) -> int:
    """
    Normaliza tickets existentes para o formato
    compartilhado com o Dashboard.
    """

    dados = await _tudo_tickets()

    lista = dados.get(
        str(guild_id),
        [],
    )

    alterado = False

    for ticket in lista:

        if not isinstance(
            ticket,
            dict,
        ):
            continue

        if not ticket.get("id"):

            ticket["id"] = str(
                uuid.uuid4()
            )[:8]

            alterado = True

        if "guild_id" not in ticket:

            ticket["guild_id"] = (
                guild_id
            )

            alterado = True

        if "status" not in ticket:

            ticket["status"] = "aberto"

            alterado = True

        if "criado_em" not in ticket:

            ticket["criado_em"] = (
                time.time()
            )

            alterado = True

    if alterado:

        dados[str(guild_id)] = lista

        await _salvar_tickets(
            dados
        )

    return len(lista)