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
    "canal_guerras_id": 1545834530085142678,

    # ========================================================
    # COMPETITIVO
    # ========================================================

    "canal_desafios_id": 1545834386128375909,
    "desafio_cooldown_minutos": 60,

    "canal_lutas_id": 1545834447944028170,
    "canal_provas_pvp_id": 1545853928736952420,
    "canal_ranking_id": 1545834182406574241,

    # ========================================================
    # MISSÕES
    # ========================================================

    "canal_missoes_missao_id": 1556543214885019668,
    "canal_provas_missao_id": 1556543417843056641,

    # ========================================================
    # CONTRIBUIÇÕES
    # ========================================================

    "canal_missoes_contribuicao_id": 1556543539213639760,
    "canal_provas_contribuicao_id": 1556543628296593448,

    # ========================================================
    # MISSÕES ESPECIAIS
    # ========================================================

    "canal_missoes_especial_id": 1556543708478972015,
    "canal_provas_especial_id": 1556543872534839336,

    # ========================================================
    # RECORDES
    # ========================================================

    "canal_recordes_id": 1545834618182303874,
}


# ============================================================
# CAMPOS QUE REPRESENTAM IDs DO DISCORD
# ============================================================

CAMPOS_ID = (
    "support_role_id",
    "log_channel_id",
    "ticket_category_id",

    "canal_eventos_id",
    "canal_parcerias_id",
    "cargo_categoria_parcerias_id",

    "canal_auditoria_id",
    "canal_guerras_id",

    "canal_desafios_id",
    "canal_lutas_id",
    "canal_provas_pvp_id",
    "canal_ranking_id",

    "canal_missoes_missao_id",
    "canal_provas_missao_id",

    "canal_missoes_contribuicao_id",
    "canal_provas_contribuicao_id",

    "canal_missoes_especial_id",
    "canal_provas_especial_id",

    "canal_recordes_id",
)


# ============================================================
# NORMALIZAÇÃO DOS IDs
# ============================================================

def _normalizar_id(valor):
    """
    Converte IDs vindos do dashboard/Upstash para int.

    O site pode salvar IDs como strings, por exemplo:
        "1545838386944938024"

    O discord.py espera:
        1545838386944938024
    """

    if valor is None or valor == "":
        return None

    try:
        return int(valor)

    except (TypeError, ValueError):
        return None


def _normalizar_config(config: dict) -> dict:

    resultado = {
        **PADRAO,
        **(config or {}),
    }

    # --------------------------------------------------------
    # Normaliza todos os IDs Discord
    # --------------------------------------------------------

    for campo in CAMPOS_ID:
        resultado[campo] = _normalizar_id(
            resultado.get(campo)
        )

    # --------------------------------------------------------
    # Canais de cargo automático
    # --------------------------------------------------------

    canais_cargo = resultado.get(
        "canais_cargo_automatico",
        {},
    )

    if not isinstance(canais_cargo, dict):
        canais_cargo = {}

    resultado["canais_cargo_automatico"] = {
        str(canal_id): int(cargo_id)
        for canal_id, cargo_id in canais_cargo.items()
        if _normalizar_id(canal_id) is not None
        and _normalizar_id(cargo_id) is not None
    }

    # --------------------------------------------------------
    # Contadores
    # --------------------------------------------------------

    contadores = resultado.get(
        "contadores",
        [],
    )

    if not isinstance(contadores, list):
        contadores = []

    resultado["contadores"] = contadores

    return resultado


# ============================================================
# STORAGE
# ============================================================

async def _tudo():
    return await carregar(
        ARQUIVO,
        {},
    )


# ============================================================
# OBTER CONFIGURAÇÃO
# ============================================================

async def get_config(
    guild_id: int,
) -> dict:

    dados = await _tudo()

    config = dados.get(
        str(guild_id),
        {},
    )

    return _normalizar_config(config)


# ============================================================
# SALVAR CONFIGURAÇÃO
# ============================================================

async def set_config(
    guild_id: int,
    **campos,
) -> dict:

    dados = await _tudo()

    atual = _normalizar_config(
        dados.get(
            str(guild_id),
            {},
        )
    )

    for chave, valor in campos.items():

        if valor is not None:

            if chave in CAMPOS_ID:
                valor = _normalizar_id(valor)

            atual[chave] = valor

    dados[str(guild_id)] = atual

    await salvar(
        ARQUIVO,
        dados,
    )

    return atual


# ============================================================
# CARGOS AUTOMÁTICOS
# ============================================================

async def definir_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
    cargo_id: int,
):

    dados = await _tudo()

    atual = _normalizar_config(
        dados.get(
            str(guild_id),
            {},
        )
    )

    mapa = atual.setdefault(
        "canais_cargo_automatico",
        {},
    )

    mapa[str(canal_id)] = int(cargo_id)

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

    atual = _normalizar_config(
        dados.get(
            str(guild_id),
            {},
        )
    )

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


# ============================================================
# CONTADORES
# ============================================================

async def adicionar_contador(
    guild_id: int,
    tipo: str,
    canal_id: int,
    cargo_id: int = None,
):

    dados = await _tudo()

    atual = _normalizar_config(
        dados.get(
            str(guild_id),
            {},
        )
    )

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
            "canal_id": int(canal_id),
            "cargo_id": (
                int(cargo_id)
                if cargo_id is not None
                else None
            ),
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

    atual = _normalizar_config(
        dados.get(
            str(guild_id),
            {},
        )
    )

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