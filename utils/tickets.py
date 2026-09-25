import unicodedata
from utils.storage import carregar, salvar

ARQUIVO_TIPOS = "ticket_tipos.json"  # { guild_id: [ {tipo...}, ... ] }

TIPOS_PADRAO = [
    {"valor": "duvidas", "label": "Dúvidas", "emoji": "❓",
     "descricao": "Clique aqui, para tirar as suas dúvidas!", "usa_ia": True},
    {"valor": "recompensas", "label": "Reivindicar recompensas", "emoji": "🎁",
     "descricao": "Reivindique aqui as suas recompensas.", "usa_ia": False},
    {"valor": "patrocinar", "label": "Patrocinar", "emoji": "📣",
     "descricao": "Clique aqui, para patrocinar o servidor/projeto!", "usa_ia": False},
    {"valor": "vip", "label": "Obter VIP", "emoji": "👑",
     "descricao": "Clique aqui, para adquirir uma VIP!", "usa_ia": False},
    {"valor": "destacar", "label": "Destacar", "emoji": "✨",
     "descricao": "Destaque aqui o seu servidor/projeto.", "usa_ia": False},
    {"valor": "outro", "label": "Outro", "emoji": "🔁",
     "descricao": "A sua opção não está acima? Clique aqui!", "usa_ia": False},
]


def _slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return "_".join(texto.split())


async def _tudo():
    return await carregar(ARQUIVO_TIPOS, {})


async def get_tipos(guild_id: int) -> list:
    dados = await _tudo()
    return dados.get(str(guild_id)) or list(TIPOS_PADRAO)


async def set_tipos(guild_id: int, lista: list):
    dados = await _tudo()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_TIPOS, dados)


async def adicionar_tipo(guild_id: int, label: str, descricao: str, emoji: str, usa_ia: bool) -> dict:
    tipos = await get_tipos(guild_id)
    tipo = {"valor": _slug(label), "label": label, "emoji": emoji, "descricao": descricao, "usa_ia": usa_ia}
    tipos = [t for t in tipos if t["valor"] != tipo["valor"]]
    tipos.append(tipo)
    await set_tipos(guild_id, tipos)
    return tipo


async def remover_tipo(guild_id: int, valor: str) -> bool:
    tipos = await get_tipos(guild_id)
    nova_lista = [t for t in tipos if t["valor"] != valor]
    if len(nova_lista) == len(tipos):
        return False
    await set_tipos(guild_id, nova_lista)
    return True


def construir_topic(user_id: int, tipo: str) -> str:
    return f"ticket-owner:{user_id}:tipo:{tipo}"


def parse_topic(topic: str):
    if not topic or not topic.startswith("ticket-owner:"):
        return None
    resto = topic[len("ticket-owner:"):]
    if ":tipo:" in resto:
        owner_id, tipo = resto.split(":tipo:", 1)
    else:
        owner_id, tipo = resto, "outro"  # tickets antigos, abertos antes dessa mudança
    return {"owner_id": owner_id, "tipo": tipo}