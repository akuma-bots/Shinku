from utils.storage import carregar, atualizar_json


ARQUIVO = "guild_configs.json"

# Evita que atualizações simultâneas sobrescrevam campos umas das outras.


# ============================================================
# CONFIGURAÇÃO OFICIAL DA NÊMESIS
# ============================================================

PADRAO = {
    "support_role_id": 1547307501345579219,
    "ticket_category_id": 1545835749369446603,

    "canais_cargo_automatico": {},

    "canal_eventos_id": 1545835097830334536,
    "canal_parcerias_id": 1545831702444777492,
    "cargo_categoria_parcerias_id": 1553019315664461934,

    "contadores": [],

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
    "ticket_category_id",

    "canal_eventos_id",
    "canal_parcerias_id",
    "cargo_categoria_parcerias_id",

    "canal_guerras_id",

    "canal_desafios_id",
    "canal_lutas_id",
    "canal_provas_pvp_id",
    "canal_ranking_id",
    "ranking_mensagem_id",
    "ticket_painel_canal_id",
    "ticket_painel_mensagem_id",

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
    Converte IDs de configuração persistidos para int.

    IDs podem estar salvos como strings, por exemplo:
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

async def _atualizar_config(guild_id: int, transformador):
    chave = str(guild_id)

    def aplicar(dados):
        if not isinstance(dados, dict):
            dados = {}
        atual = _normalizar_config(dados.get(chave, {}))
        transformador(atual)
        dados[chave] = _normalizar_config(atual)
        return dados

    dados = await atualizar_json(ARQUIVO, {}, aplicar)
    return _normalizar_config(dados.get(chave, {}))


async def set_config(
    guild_id: int,
    **campos,
) -> dict:
    def aplicar(atual):
        for chave, valor in campos.items():
            if valor is not None:
                if chave in CAMPOS_ID:
                    valor = _normalizar_id(valor)
                atual[chave] = valor

    return await _atualizar_config(guild_id, aplicar)


async def definir_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
    cargo_id: int,
):
    def aplicar(atual):
        mapa = atual.setdefault("canais_cargo_automatico", {})
        mapa[str(canal_id)] = int(cargo_id)

    atual = await _atualizar_config(guild_id, aplicar)
    return atual["canais_cargo_automatico"]


async def remover_canal_cargo_automatico(
    guild_id: int,
    canal_id: int,
):
    def aplicar(atual):
        mapa = atual.setdefault("canais_cargo_automatico", {})
        mapa.pop(str(canal_id), None)

    atual = await _atualizar_config(guild_id, aplicar)
    return atual["canais_cargo_automatico"]


async def adicionar_contador(
    guild_id: int,
    tipo: str,
    canal_id: int,
    cargo_id: int = None,
):
    def aplicar(atual):
        lista = atual.setdefault("contadores", [])
        lista[:] = [
            contador for contador in lista
            if contador.get("canal_id") != int(canal_id)
        ]
        lista.append({
            "tipo": str(tipo or "").strip(),
            "canal_id": int(canal_id),
            "cargo_id": int(cargo_id) if cargo_id is not None else None,
        })

    atual = await _atualizar_config(guild_id, aplicar)
    return atual["contadores"]


async def remover_contador(
    guild_id: int,
    canal_id: int,
):
    def aplicar(atual):
        lista = atual.setdefault("contadores", [])
        lista[:] = [
            contador for contador in lista
            if contador.get("canal_id") != int(canal_id)
        ]

    atual = await _atualizar_config(guild_id, aplicar)
    return atual["contadores"]


# ============================================================
# AUTORIZAÇÃO CENTRAL DA NÊMESIS
# ============================================================

import discord
from discord import app_commands

GUILD_NEMESIS_ID = 1563995879981981817
CARGO_ACESSO_NEMESIS_ID = 1563995879990624372

# Administração: somente cargos acima de Supervisor Staff.
CARGO_OCTOGONO_ID = 1563995880007139425
CARGOS_LIDERANCA_IDS = frozenset({
    CARGO_OCTOGONO_ID,
    1563995880007139424,  # Diretor Staff
    1563995880007139423,  # Vice-Diretor Staff
})

# Cargos acima de Elite podem promover, rebaixar e banir.
CARGOS_ACIMA_ELITE_IDS = frozenset({
    1563995879998754938,  # Veterano
    1563995879998754939,  # Treinador
    1563995879998754940,  # Comandante
    1563995879998754941,  # Vice Capitão
    1563995879998754942,  # Capitão
    1563995879998754943,  # Capitão Geral
})


def _membro_nemesis(membro) -> bool:
    return bool(
        isinstance(membro, discord.Member)
        and membro.guild.id == GUILD_NEMESIS_ID
    )


def membro_tem_lideranca(membro) -> bool:
    return bool(
        _membro_nemesis(membro)
        and any(cargo.id in CARGOS_LIDERANCA_IDS for cargo in membro.roles)
    )


def membro_tem_octogono(membro) -> bool:
    return bool(
        _membro_nemesis(membro)
        and any(cargo.id == CARGO_OCTOGONO_ID for cargo in membro.roles)
    )


def membro_pode_promover_rebaixar_banir(membro) -> bool:
    return bool(
        _membro_nemesis(membro)
        and any(cargo.id in CARGOS_ACIMA_ELITE_IDS for cargo in membro.roles)
    )


def membro_tem_acesso_nemesis(membro) -> bool:
    return bool(
        isinstance(membro, discord.Member)
        and membro.guild.id == GUILD_NEMESIS_ID
        and (
            membro_tem_lideranca(membro)
            or any(cargo.id == CARGO_ACESSO_NEMESIS_ID for cargo in membro.roles)
        )
    )


async def verificar_lideranca(interaction: discord.Interaction) -> bool:
    return membro_tem_lideranca(interaction.user)


async def verificar_octogono(interaction: discord.Interaction) -> bool:
    return membro_tem_octogono(interaction.user)


async def verificar_hierarquia(interaction: discord.Interaction) -> bool:
    return membro_pode_promover_rebaixar_banir(interaction.user)


def lideranca_only():
    """Restringe administração aos cargos acima de Supervisor Staff."""
    return app_commands.check(verificar_lideranca)


def octogono_only():
    """Restringe gestão de missões ao cargo OCTÓGONO."""
    return app_commands.check(verificar_octogono)


def hierarquia_only():
    """Autoriza ações hierárquicas apenas aos cargos acima de Elite."""
    return app_commands.check(verificar_hierarquia)
