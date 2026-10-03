from utils.storage import carregar, salvar


ARQUIVO = "guild_configs.json"


# ============================================================
# CONFIGURAÇÃO OFICIAL DA NÊMESIS
# ============================================================

PADRAO = {
    "support_role_id": 1549832967495491645,

    "log_channel_id": 1545838386944938024,

    "ticket_category_id": 1545835749369446603,

    "canais_cargo_automatico": {},

    "canal_eventos_id": 1545835097830334536,

    "canal_parcerias_id": 1545831702444777492,

    "cargo_categoria_parcerias_id": 1553019315664461934,

    "contadores": [],

    "canal_auditoria_id": 1545838575449276478,

    "canal_desafios_id": 1545834386128375909,

    "desafio_cooldown_minutos": 60,

    "canal_lutas_id": 1545834447944028170,
}


async def _tudo():
    return await carregar(
        ARQUIVO,
        {},
    )


async def get_config(
    guild_id: int,
) -> dict:

    dados = await _tudo()

    config = dados.get(
        str(guild_id),
        {},
    )

    resultado = {
        **PADRAO,
        **config,
    }

    resultado[
        "canais_cargo_automatico"
    ] = config.get(
        "canais_cargo_automatico",
        {},
    )

    resultado[
        "contadores"
    ] = config.get(
        "contadores",
        [],
    )

    return resultado


async def set_config(
    guild_id: int,
    **campos,
) -> dict:

    dados = await _tudo()

    atual = {
        **PADRAO,
        **dados.get(
            str(guild_id),
            {},
        ),
    }

    for chave, valor in campos.items():

        if valor is not None:
            atual[chave] = valor

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return atual


async def definir_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
    cargo_id: int,
):

    dados = await _tudo()

    atual = {
        **PADRAO,
        **dados.get(
            str(guild_id),
            {},
        ),
    }

    mapa = atual.setdefault(
        "canais_cargo_automatico",
        {},
    )

    mapa[str(canal_id)] = cargo_id

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return mapa


async def remover_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
):

    dados = await _tudo()

    atual = {
        **PADRAO,
        **dados.get(
            str(guild_id),
            {},
        ),
    }

    mapa = atual.setdefault(
        "canais_cargo_automatico",
        {},
    )

    mapa.pop(
        str(canal_id),
        None,
    )

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return mapa


async def adicionar_contador(
    guild_id: int,
    tipo: str,
    canal_id: int,
    cargo_id: int = None,
):

    dados = await _tudo()

    atual = {
        **PADRAO,
        **dados.get(
            str(guild_id),
            {},
        ),
    }

    lista = atual.setdefault(
        "contadores",
        [],
    )

    lista[:] = [
        contador
        for contador in lista
        if contador["canal_id"] != canal_id
    ]

    lista.append(
        {
            "tipo": tipo,
            "canal_id": canal_id,
            "cargo_id": cargo_id,
        }
    )

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return lista


async def remover_contador(
    guild_id: int,
    canal_id: int,
):

    dados = await _tudo()

    atual = {
        **PADRAO,
        **dados.get(
            str(guild_id),
            {},
        ),
    }

    lista = atual.setdefault(
        "contadores",
        [],
    )

    lista[:] = [
        contador
        for contador in lista
        if contador["canal_id"] != canal_id
    ]

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return lista