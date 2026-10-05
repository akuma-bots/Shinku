from utils.storage import carregar, salvar
from utils.competitivo_sync import somar_pontos_competitivo


ARQUIVO_PERFIS = "perfis.json"
ARQUIVO_PATENTES = "patentes_config.json"


PADRAO_PERFIL = {
    "xp": 0,
    "patente": None,
    "vitorias": 0,
    "derrotas": 0,
    "kills": 0,
    "deaths": 0,
    "mvps": 0,
    "sequencia_atual": 0,
    "maior_sequencia": 0,
    "medalhas": [],
}


XP_VITORIA = 30
XP_DERROTA = 10
XP_BONUS_MVP = 20


async def get_perfil(
    guild_id: int,
    user_id: int,
) -> dict:

    todos = await carregar(
        ARQUIVO_PERFIS,
        {},
    )

    perfil = todos.get(
        str(guild_id),
        {},
    ).get(
        str(user_id),
        {},
    )

    return {
        **PADRAO_PERFIL,
        **perfil,
        "medalhas": list(
            perfil.get("medalhas", [])
        ),
    }


async def _salvar_perfil(
    guild_id: int,
    user_id: int,
    perfil: dict,
):

    todos = await carregar(
        ARQUIVO_PERFIS,
        {},
    )

    guild_dados = todos.setdefault(
        str(guild_id),
        {},
    )

    guild_dados[str(user_id)] = perfil

    await salvar(
        ARQUIVO_PERFIS,
        todos,
    )


async def get_patentes(
    guild_id: int,
) -> list:

    todas = await carregar(
        ARQUIVO_PATENTES,
        {},
    )

    lista = todas.get(
        str(guild_id),
        [],
    )

    return sorted(
        lista,
        key=lambda p: p["xp_minimo"],
    )


async def salvar_patentes(
    guild_id: int,
    lista: list,
):

    todas = await carregar(
        ARQUIVO_PATENTES,
        {},
    )

    todas[str(guild_id)] = lista

    await salvar(
        ARQUIVO_PATENTES,
        todas,
    )


def _checar_novas_medalhas(
    perfil: dict,
) -> list:

    candidatas = []

    if perfil["vitorias"] == 1:
        candidatas.append(
            "🥉 Primeira Vitória"
        )

    if perfil["vitorias"] >= 10:
        candidatas.append(
            "🥈 Veterano (10 vitórias)"
        )

    if perfil["vitorias"] >= 50:
        candidatas.append(
            "🥇 Lenda (50 vitórias)"
        )

    if perfil["mvps"] >= 5:
        candidatas.append(
            "⭐ MVP Frequente (5 MVPs)"
        )

    if perfil["maior_sequencia"] >= 5:
        candidatas.append(
            "🔥 Sequência de 5"
        )

    if perfil["maior_sequencia"] >= 10:
        candidatas.append(
            "🔥🔥 Sequência de 10"
        )

    return [
        medalha
        for medalha in candidatas
        if medalha not in perfil["medalhas"]
    ]


async def registrar_resultado_guerra(
    guild_id: int,
    user_id: int,
    venceu: bool,
    foi_mvp: bool = False,
) -> dict:

    perfil = await get_perfil(
        guild_id,
        user_id,
    )

    patente_antiga = perfil["patente"]

    if venceu:

        perfil["vitorias"] += 1

        perfil["sequencia_atual"] += 1

        perfil["maior_sequencia"] = max(
            perfil["maior_sequencia"],
            perfil["sequencia_atual"],
        )

        perfil["xp"] += XP_VITORIA

    else:

        perfil["derrotas"] += 1

        perfil["sequencia_atual"] = 0

        perfil["xp"] += XP_DERROTA

    if foi_mvp:

        perfil["mvps"] += 1

        perfil["xp"] += XP_BONUS_MVP

    medalhas_novas = _checar_novas_medalhas(
        perfil
    )

    perfil["medalhas"].extend(
        medalhas_novas
    )

    # Salva o perfil antigo do bot.
    await _salvar_perfil(
        guild_id,
        user_id,
        perfil,
    )

    # ==========================================================
    # SINCRONIZAÇÃO COM O DASHBOARD
    # ==========================================================

    delta_pontos = (
        (XP_VITORIA if venceu else XP_DERROTA)
        + (10 if venceu else 0)
        + (XP_BONUS_MVP if foi_mvp else 0)
    )

    await somar_pontos_competitivo(
        user_id=user_id,
        delta=delta_pontos,
        vitorias=perfil["vitorias"],
        derrotas=perfil["derrotas"],
    )

    return {
        "perfil": perfil,
        "medalhas_novas": medalhas_novas,
        "patente_antiga": patente_antiga,
    }


async def registrar_pvp(
    guild_id: int,
    vencedor_id: int,
    perdedor_id: int,
) -> tuple:

    perfil_vencedor = await get_perfil(
        guild_id,
        vencedor_id,
    )

    perfil_vencedor["kills"] += 1

    await _salvar_perfil(
        guild_id,
        vencedor_id,
        perfil_vencedor,
    )

    perfil_perdedor = await get_perfil(
        guild_id,
        perdedor_id,
    )

    perfil_perdedor["deaths"] += 1

    await _salvar_perfil(
        guild_id,
        perdedor_id,
        perfil_perdedor,
    )

    return (
        perfil_vencedor,
        perfil_perdedor,
    )


async def calcular_patente_atual(
    guild_id: int,
    xp: int,
):

    patentes = await get_patentes(
        guild_id
    )

    atingida = None

    for patente in patentes:

        if xp >= patente["xp_minimo"]:
            atingida = patente

    return atingida


async def definir_patente(
    guild_id: int,
    user_id: int,
    nome_patente: str,
):

    perfil = await get_perfil(
        guild_id,
        user_id,
    )

    perfil["patente"] = nome_patente

    await _salvar_perfil(
        guild_id,
        user_id,
        perfil,
    )

    return perfil


def kdr(
    perfil: dict,
) -> float:

    if perfil["deaths"] > 0:

        return round(
            perfil["kills"]
            / perfil["deaths"],
            2,
        )

    return float(
        perfil["kills"]
    )