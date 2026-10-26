import asyncio
from utils.storage import carregar, salvar


ARQUIVO = "guild_configs.json"

# Evita que atualizações simultâneas sobrescrevam campos umas das outras.
_CONFIG_LOCK = asyncio.Lock()


# ============================================================
# CONFIGURAÇÃO OFICIAL DA NÊMESIS
# ============================================================

PADRAO = {
    "support_role_id": 1563995879998754946,
    "log_channel_id": 1563995882234450005,
    "ticket_category_id": 1563995881655509056,

    "canais_cargo_automatico": {},

    "canal_eventos_id": 1563995880623841336,
    "canal_parcerias_id": 1563995881655509058,
    "cargo_categoria_parcerias_id": None,

    "contadores": [],

    "canal_auditoria_id": 1563995882234450005,
    "canal_guerras_id": 1563995881655509053,

    # ========================================================
    # COMPETITIVO
    # ========================================================

    "canal_desafios_id": 1563995881508831341,
    "desafio_cooldown_minutos": 60,

    "canal_lutas_id": 1563995881655509052,
    "canal_provas_pvp_id": 1563995881655509054,
    "canal_ranking_id": 1563995881508831338,

    # ========================================================
    # MISSÕES
    # ========================================================

    "canal_missoes_missao_id": 1563995881315897549,
    "canal_provas_missao_id": 1563995882540498998,

    # ========================================================
    # CONTRIBUIÇÕES
    # ========================================================

    "canal_missoes_contribuicao_id": 1563995881315897551,
    "canal_provas_contribuicao_id": 1563995882540498999,

    # ========================================================
    # MISSÕES ESPECIAIS
    # ========================================================

    "canal_missoes_especial_id": 1563995880623841336,
    "canal_provas_especial_id": 1563995882540499000,

    # ========================================================
    # RECORDES
    # ========================================================

    "canal_recordes_id": 1563995881655509055,
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



# Valores legados migrados para os IDs confirmados no inventário do servidor atual.
# None indica que o cargo equivalente ainda não existe no inventário recebido.
MIGRACAO_IDS = {
    "support_role_id": {1547307501345579219: 1563995879998754946},
    "log_channel_id": {1545838386944938024: 1563995882234450005},
    "ticket_category_id": {1545835749369446603: 1563995881655509056},
    "canal_eventos_id": {1545835097830334536: 1563995880623841336},
    "canal_parcerias_id": {1545831702444777492: 1563995881655509058},
    "cargo_categoria_parcerias_id": {1553019315664461934: None},
    "canal_auditoria_id": {1545837705609617428: 1563995882234450005},
    "canal_guerras_id": {1545834530085142678: 1563995881655509053},
    "canal_desafios_id": {1545834386128375909: 1563995881508831341},
    "canal_lutas_id": {1545834447944028170: 1563995881655509052},
    "canal_provas_pvp_id": {1545853928736952420: 1563995881655509054},
    "canal_ranking_id": {1545834182406574241: 1563995881508831338},
    "canal_missoes_missao_id": {1556543214885019668: 1563995881315897549},
    "canal_provas_missao_id": {1556543417843056641: 1563995882540498998},
    "canal_missoes_contribuicao_id": {1556543539213639760: 1563995881315897551},
    "canal_provas_contribuicao_id": {1556543628296593448: 1563995882540498999},
    "canal_missoes_especial_id": {1556543708478972015: 1563995880623841336},
    "canal_provas_especial_id": {1556543872534839336: 1563995882540499000},
    "canal_recordes_id": {1545834618182303874: 1563995881655509055},
}

# ============================================================
# NORMALIZAÇÃO DOS IDs
# ============================================================

def _normalizar_id(valor):
    """
    Converte IDs de configuração persistidos para int.

    IDs podem estar salvos como strings, por exemplo:
        "1563995882234450005"

    O discord.py espera:
        1563995882234450005
    """

    if valor is None or valor == "":
        return None

    try:
        return int(valor)

    except (TypeError, ValueError):
        return None


def _normalizar_config(config: dict) -> dict:
    if not isinstance(config, dict):
        config = {}

    resultado = {
        **PADRAO,
        **config,
    }

    # Migra automaticamente o antigo cargo de suporte para o cargo oficial.
    if _normalizar_id(resultado.get("support_role_id")) == 1549832967495491645:
        resultado["support_role_id"] = PADRAO["support_role_id"]

    # --------------------------------------------------------
    # Migra IDs antigos persistidos antes da normalização.
    # Assim, configs salvas não sobrescrevem os novos padrões.
    # --------------------------------------------------------

    for campo, mapa in MIGRACAO_IDS.items():
        valor_legado = _normalizar_id(resultado.get(campo))
        if valor_legado in mapa:
            resultado[campo] = mapa[valor_legado]

    # --------------------------------------------------------
    # Normaliza todos os IDs Discord
    # --------------------------------------------------------

    for campo in CAMPOS_ID:
        valor = _normalizar_id(resultado.get(campo))
        # Valores vazios no storage não devem apagar os canais padrão.
        if valor is None and campo in PADRAO:
            valor = _normalizar_id(PADRAO.get(campo))
        resultado[campo] = valor

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

    contadores = resultado.get("contadores", [])
    if not isinstance(contadores, list):
        contadores = []

    contadores_validos = []
    for contador in contadores:
        if not isinstance(contador, dict):
            continue
        canal_id = _normalizar_id(contador.get("canal_id"))
        if canal_id is None:
            continue
        cargo_id = _normalizar_id(contador.get("cargo_id"))
        contadores_validos.append({
            **contador,
            "tipo": str(contador.get("tipo") or "").strip(),
            "canal_id": canal_id,
            "cargo_id": cargo_id,
        })

    resultado["contadores"] = contadores_validos

    return resultado


# ============================================================
# STORAGE
# ============================================================

async def _tudo():
    dados = await carregar(ARQUIVO, {})
    return dados if isinstance(dados, dict) else {}


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
    async with _CONFIG_LOCK:
        dados = await _tudo()
        atual = _normalizar_config(dados.get(str(guild_id), {}))

        for chave, valor in campos.items():
            if valor is not None:
                if chave in CAMPOS_ID:
                    valor = _normalizar_id(valor)
                atual[chave] = valor

        dados[str(guild_id)] = atual
        await salvar(ARQUIVO, dados)
        return atual

async def definir_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
    cargo_id: int,
):
    async with _CONFIG_LOCK:
        dados = await _tudo()
        atual = _normalizar_config(dados.get(str(guild_id), {}))
        mapa = atual.setdefault("canais_cargo_automatico", {})
        mapa[str(canal_id)] = int(cargo_id)
        dados[str(guild_id)] = atual
        await salvar(ARQUIVO, dados)
        return mapa

async def remover_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
):
    async with _CONFIG_LOCK:
        dados = await _tudo()
        atual = _normalizar_config(dados.get(str(guild_id), {}))
        mapa = atual.setdefault("canais_cargo_automatico", {})
        mapa.pop(str(canal_id), None)
        dados[str(guild_id)] = atual
        await salvar(ARQUIVO, dados)
        return mapa

async def adicionar_contador(
    guild_id: int,
    tipo: str,
    canal_id: int,
    cargo_id: int = None,
):
    async with _CONFIG_LOCK:
        dados = await _tudo()
        atual = _normalizar_config(dados.get(str(guild_id), {}))
        lista = atual.setdefault("contadores", [])
        lista[:] = [
            contador for contador in lista
            if contador.get("canal_id") != canal_id
        ]
        lista.append({
            "tipo": tipo,
            "canal_id": int(canal_id),
            "cargo_id": int(cargo_id) if cargo_id is not None else None,
        })
        dados[str(guild_id)] = atual
        await salvar(ARQUIVO, dados)
        return lista

async def remover_contador(
    guild_id: int,
    canal_id: int,
):
    async with _CONFIG_LOCK:
        dados = await _tudo()
        atual = _normalizar_config(dados.get(str(guild_id), {}))
        lista = atual.setdefault("contadores", [])
        lista[:] = [
            contador for contador in lista
            if contador.get("canal_id") != canal_id
        ]
        dados[str(guild_id)] = atual
        await salvar(ARQUIVO, dados)
        return lista

