import time
import uuid
import unicodedata

from utils.storage import carregar, atualizar_json


ARQUIVO_TIPOS = "ticket_tipos.json"
ARQUIVO_TICKETS = "tickets.json"


TIPOS_PADRAO = [
    {"valor": "recrutamento", "label": "Recrutamento e Admissão", "emoji": "✦", "descricao": "Inicie sua candidatura e obtenha informações sobre os critérios e as etapas de admissão à NÊMESIS.", "usa_ia": False},
    {"valor": "hierarquia_divisoes", "label": "Estrutura e Hierarquia", "emoji": "♟️", "descricao": "Solicite esclarecimentos sobre a estrutura organizacional, atribuições, divisões e progressão hierárquica.", "usa_ia": False},
    {"valor": "conflitos_denuncias", "label": "Integridade e Conduta", "emoji": "⚖️", "descricao": "Comunique ocorrências, violações de normas ou questões disciplinares para análise da administração.", "usa_ia": False},
    {"valor": "guerras_desafios", "label": "Operações Competitivas", "emoji": "⚔️", "descricao": "Encaminhe assuntos relacionados a confrontos oficiais, desafios, disputas PvP e guerras entre guildas.", "usa_ia": False},
    {"valor": "suporte_comunidade", "label": "Assistência Técnica", "emoji": "⚙️", "descricao": "Solicite suporte para questões técnicas relacionadas ao servidor, ao bot, aos comandos e aos sistemas da comunidade.", "usa_ia": False},
    {"valor": "aliancas", "label": "Relações Institucionais", "emoji": "🤝", "descricao": "Apresente propostas de aliança, parceria ou cooperação institucional entre a NÊMESIS e outras comunidades.", "usa_ia": False},
    {"valor": "eventos_atividades", "label": "Gestão de Eventos", "emoji": "🏆", "descricao": "Solicite informações e assistência referentes à organização, às inscrições e à participação em eventos e competições oficiais.", "usa_ia": False},
    {"valor": "sugestoes_projetos", "label": "Premiações e Reconhecimentos", "emoji": "🎖️", "descricao": "Solicite a validação, a atribuição ou o resgate de premiações obtidas em eventos, competições, sorteios e campanhas oficiais.", "usa_ia": False},
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
    if not isinstance(dados, dict):
        dados = {}
    tipos = dados.get(str(guild_id))
    if not isinstance(tipos, list):
        return list(TIPOS_PADRAO)
    return [item for item in tipos if isinstance(item, dict)]


async def set_tipos(guild_id: int, lista: list):
    if not isinstance(lista, list):
        raise TypeError("A lista de categorias de tickets precisa ser uma lista.")

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        dados[str(guild_id)] = lista
        return dados

    await atualizar_json(ARQUIVO_TIPOS, {}, aplicar)


async def adicionar_tipo(
    guild_id: int,
    label: str,
    descricao: str,
    emoji: str,
    usa_ia: bool,
) -> dict:
    tipo = {
        "valor": _slug(label),
        "label": str(label).strip()[:100],
        "emoji": str(emoji)[:100],
        "descricao": str(descricao)[:500],
        "usa_ia": bool(usa_ia),
    }

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        tipos = dados.get(str(guild_id))
        if not isinstance(tipos, list):
            tipos = list(TIPOS_PADRAO)
        tipos = [
            item for item in tipos
            if isinstance(item, dict) and item.get("valor") != tipo["valor"]
        ]
        tipos.append(tipo)
        dados[str(guild_id)] = tipos
        return dados

    await atualizar_json(ARQUIVO_TIPOS, {}, aplicar)
    return tipo


async def atualizar_tipo_visual(
    guild_id: int,
    valor: str,
    emoji: str,
    descricao: str,
    nome: str = None,
):
    resultado = {"tipo": None}

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        tipos = dados.get(str(guild_id))
        if not isinstance(tipos, list):
            tipos = list(TIPOS_PADRAO)
        alvo = next(
            (item for item in tipos if isinstance(item, dict) and item.get("valor") == valor),
            None,
        )
        if alvo is not None:
            alvo["emoji"] = str(emoji)[:64]
            alvo["descricao"] = str(descricao)[:100]
            if nome:
                alvo["label"] = str(nome)[:100]
            resultado["tipo"] = dict(alvo)
        dados[str(guild_id)] = tipos
        return dados

    await atualizar_json(ARQUIVO_TIPOS, {}, aplicar)
    return resultado["tipo"]


async def remover_tipo(guild_id: int, valor: str) -> bool:
    resultado = {"removido": False}

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        tipos = dados.get(str(guild_id))
        if not isinstance(tipos, list):
            tipos = list(TIPOS_PADRAO)
        novos = [
            item for item in tipos
            if not isinstance(item, dict) or item.get("valor") != valor
        ]
        resultado["removido"] = len(novos) != len(tipos)
        dados[str(guild_id)] = novos
        return dados

    await atualizar_json(ARQUIVO_TIPOS, {}, aplicar)
    return resultado["removido"]


def construir_topic(
    user_id: int,
    tipo: str,
) -> str:

    return (
        f"ticket-owner:{user_id}:tipo:{tipo}"
    )


def parse_topic(topic: str):
    if not isinstance(topic, str) or not topic.startswith("ticket-owner:"):
        return None

    resto = topic[len("ticket-owner:"):]
    if ":tipo:" in resto:
        owner_id, tipo = resto.split(":tipo:", 1)
    else:
        owner_id, tipo = resto, "outro"

    if not owner_id.isdigit() or len(owner_id) > 20 or int(owner_id) <= 0:
        return None
    tipo = tipo.strip() or "outro"
    if len(tipo) > 100 or any(ord(caractere) < 32 for caractere in tipo):
        return None

    return {
        "owner_id": owner_id,
        "tipo": tipo,
    }


# ==========================================================
# TICKETS
# ==========================================================


async def _tudo_tickets():
    return await carregar(ARQUIVO_TICKETS, {})


async def _atualizar_tickets(guild_id: int, transformador):
    chave = str(guild_id)

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        lista = dados.get(chave)
        if not isinstance(lista, list):
            lista = []
        resultado = transformador(lista)
        dados[chave] = lista if resultado is None else resultado
        return dados

    dados = await atualizar_json(ARQUIVO_TICKETS, {}, aplicar)
    lista = dados.get(chave, [])
    return lista if isinstance(lista, list) else []


async def listar_tickets(
    guild_id: int,
    status: str = None,
) -> list:

    dados = await _tudo_tickets()
    if not isinstance(dados, dict):
        return []
    lista = dados.get(str(guild_id), [])
    if not isinstance(lista, list):
        return []
    lista = [ticket for ticket in lista if isinstance(ticket, dict)]

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
    novo = {
        "id": str(uuid.uuid4())[:8],
        "guild_id": int(guild_id),
        "usuario_id": int(usuario_id),
        "tipo": str(tipo),
        "canal_id": int(canal_id) if canal_id is not None else None,
        "mensagem_id": int(mensagem_id) if mensagem_id is not None else None,
        "status": "aberto",
        "criado_em": time.time(),
        "fechado_em": None,
        "fechado_por_id": None,
        "motivo_fechamento": None,
        "atendido_por_id": None,
    }
    resultado = {"ticket": None}

    def aplicar(lista):
        existente = next(
            (item for item in lista
             if str(item.get("usuario_id")) == str(usuario_id)
             and item.get("status") == "aberto"),
            None,
        )
        if existente:
            resultado["ticket"] = dict(existente)
        else:
            lista.append(novo)
            resultado["ticket"] = dict(novo)
        return lista

    await _atualizar_tickets(guild_id, aplicar)
    return resultado["ticket"]


async def atualizar_ticket(guild_id: int, ticket_id: str, **campos):
    resultado = {"ticket": None}

    def aplicar(lista):
        alvo = next((item for item in lista if item.get("id") == ticket_id), None)
        if alvo is None:
            return lista
        limpar_responsavel = bool(campos.get("limpar_responsavel"))
        for chave, valor in campos.items():
            if chave == "limpar_responsavel":
                continue
            if valor is not None:
                alvo[chave] = valor
        if limpar_responsavel:
            alvo["atendido_por_id"] = None
        resultado["ticket"] = dict(alvo)
        return lista

    await _atualizar_tickets(guild_id, aplicar)
    return resultado["ticket"]


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


async def registrar_avaliacao(
    guild_id: int,
    ticket_id: str,
    nota: int,
    feedback: str = "",
    avaliado_em: float = None,
):
    resultado = {"ticket": None, "registrada": False}
    nota = int(nota)
    if nota < 1 or nota > 5:
        raise ValueError("A avaliação precisa estar entre 1 e 5.")
    timestamp = float(avaliado_em or time.time())

    def aplicar(lista):
        alvo = next((item for item in lista if item.get("id") == ticket_id), None)
        if (
            alvo is None
            or alvo.get("status") != "fechado"
            or alvo.get("avaliacao") is not None
        ):
            return lista
        alvo["avaliacao"] = nota
        alvo["feedback"] = str(feedback)[:1000]
        alvo["avaliado_em"] = timestamp
        resultado["ticket"] = dict(alvo)
        resultado["registrada"] = True
        return lista

    await _atualizar_tickets(guild_id, aplicar)
    return resultado["ticket"] if resultado["registrada"] else None


async def iniciar_fechamento_ticket(
    guild_id: int,
    ticket_id: str,
    fechado_por_id: int = None,
    motivo: str = None,
    lease_segundos: int = 90,
) -> bool:
    """Adquire uma reserva temporária para fechar um ticket em apenas um worker."""
    agora = time.time()
    resultado = {"adquirido": False}

    def aplicar(lista):
        alvo = next((item for item in lista if item.get("id") == ticket_id), None)
        if alvo is None or alvo.get("status") == "fechado":
            return lista
        try:
            iniciado = float(alvo.get("fechamento_iniciado_em") or 0)
        except (TypeError, ValueError):
            iniciado = 0
        if (
            alvo.get("status") == "fechando"
            and agora - iniciado < max(30, int(lease_segundos))
        ):
            return lista
        alvo["status"] = "fechando"
        alvo["fechamento_iniciado_em"] = agora
        alvo["fechado_por_id"] = fechado_por_id
        alvo["motivo_fechamento"] = motivo
        resultado["adquirido"] = True
        return lista

    await _atualizar_tickets(guild_id, aplicar)
    return resultado["adquirido"]


async def finalizar_fechamento_ticket(guild_id: int, ticket_id: str):
    return await atualizar_ticket(
        guild_id,
        ticket_id,
        status="fechado",
        fechado_em=time.time(),
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


async def remover_responsavel_atendimento(guild_id: int, ticket_id: str):
    """Remove a atribuição quando a aplicação de permissões falha."""
    return await atualizar_ticket(
        guild_id, ticket_id, limpar_responsavel=True
    )


async def sincronizar_canal_ticket(
    guild_id: int,
    canal_id: int,
    mensagem_id: int = None,
    usuario_id: int = None,
    tipo: str = "outro",
):
    resultado = {"ticket": None}
    agora = time.time()

    def aplicar(lista):
        ticket = next(
            (item for item in lista if str(item.get("canal_id")) == str(canal_id)),
            None,
        )
        if ticket is None:
            ticket = {
                "id": str(uuid.uuid4())[:8],
                "guild_id": int(guild_id),
                "usuario_id": int(usuario_id or 0),
                "tipo": str(tipo or "outro"),
                "canal_id": int(canal_id),
                "mensagem_id": int(mensagem_id) if mensagem_id is not None else None,
                "status": "aberto",
                "criado_em": agora,
                "fechado_em": None,
                "fechado_por_id": None,
                "motivo_fechamento": None,
                "atendido_por_id": None,
                "recuperado": True,
            }
            lista.append(ticket)
        else:
            if mensagem_id is not None:
                ticket["mensagem_id"] = int(mensagem_id)
            if usuario_id is not None and int(usuario_id) > 0:
                ticket["usuario_id"] = int(usuario_id)
            if tipo:
                ticket["tipo"] = str(tipo)
        resultado["ticket"] = dict(ticket)
        return lista

    await _atualizar_tickets(guild_id, aplicar)
    return resultado["ticket"]
