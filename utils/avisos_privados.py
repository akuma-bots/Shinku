"""Helpers puros para o sistema de avisos privados da NÊMESIS."""

MAX_INSCRITOS = 100_000


def normalizar_estado(dados):
    """Valida e normaliza os dados persistidos sem descartar outros servidores."""
    if not isinstance(dados, dict):
        dados = {}

    guilds = dados.get("guilds")
    if not isinstance(guilds, dict):
        guilds = {}

    dados["guilds"] = guilds
    return dados


def obter_estado_guild(dados, guild_id):
    dados = normalizar_estado(dados)
    chave = str(int(guild_id))
    estado = dados["guilds"].get(chave)
    if not isinstance(estado, dict):
        estado = {}

    inscritos = estado.get("inscritos", [])
    if not isinstance(inscritos, list):
        inscritos = []

    normalizados = []
    vistos = set()
    for valor in inscritos:
        try:
            user_id = str(int(valor))
        except (TypeError, ValueError, OverflowError):
            continue
        if user_id not in vistos:
            vistos.add(user_id)
            normalizados.append(user_id)
        if len(normalizados) >= MAX_INSCRITOS:
            break

    estado["inscritos"] = normalizados
    dados["guilds"][chave] = estado
    return dados, estado


def definir_inscricao(dados, guild_id, user_id, receber):
    dados, estado = obter_estado_guild(dados, guild_id)
    user_id = str(int(user_id))
    inscritos = estado["inscritos"]

    if receber:
        if user_id not in inscritos:
            if len(inscritos) >= MAX_INSCRITOS:
                raise ValueError("O limite de inscrições foi atingido.")
            inscritos.append(user_id)
    else:
        inscritos = [item for item in inscritos if item != user_id]
        estado["inscritos"] = inscritos

    return dados, estado
