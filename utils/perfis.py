from utils.storage import carregar, salvar
from utils.competitivo_sync import somar_pontos_competitivo


ARQUIVO_PERFIS = "perfis.json"
ARQUIVO_PATENTES = "patentes_config.json"
ARQUIVO_COMPETITIVO = "competitivo.json"


PADRAO_PERFIL = {
    "xp": 0,
    "patente": None,
    "vitorias": 0,
    "derrotas": 0,
    "empates": 0,
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


def _inteiro_nao_negativo(valor, padrao: int = 0) -> int:
    """Converte estatísticas antigas para inteiros válidos sem deixar o perfil quebrar."""
    try:
        return max(0, int(valor if valor is not None else padrao))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(padrao))


def _normalizar_perfil(perfil) -> dict:
    """Completa campos ausentes e saneia dados legados sem descartar campos extras."""
    if not isinstance(perfil, dict):
        perfil = {}

    normalizado = {**PADRAO_PERFIL, **perfil}
    for campo in (
        "xp",
        "vitorias",
        "derrotas",
        "empates",
        "kills",
        "deaths",
        "mvps",
        "sequencia_atual",
        "maior_sequencia",
    ):
        normalizado[campo] = _inteiro_nao_negativo(
            normalizado.get(campo),
            PADRAO_PERFIL[campo],
        )

    medalhas = normalizado.get("medalhas", [])
    if isinstance(medalhas, str):
        medalhas = [medalhas] if medalhas.strip() else []
    elif not isinstance(medalhas, (list, tuple, set)):
        medalhas = []

    # Preserva a ordem original e remove entradas vazias/duplicadas.
    normalizado["medalhas"] = list(dict.fromkeys(
        str(medalha).strip()
        for medalha in medalhas
        if str(medalha).strip()
    ))
    normalizado["maior_sequencia"] = max(
        normalizado["maior_sequencia"],
        normalizado["sequencia_atual"],
    )
    return normalizado


async def get_perfil(
    guild_id: int,
    user_id: int,
) -> dict:
    todos = await carregar(ARQUIVO_PERFIS, {})
    guilds = todos if isinstance(todos, dict) else {}
    perfis_guild = guilds.get(str(guild_id), {})
    if not isinstance(perfis_guild, dict):
        perfis_guild = {}
    perfil = perfis_guild.get(str(user_id), {})

    # Recupera estatísticas antigas do ranking interno se o perfil local ainda não existir.
    if not isinstance(perfil, dict) or not perfil:
        competitivo = await carregar(
            ARQUIVO_COMPETITIVO,
            {"catalogo": [], "perfis": {}},
        )
        competitivos = competitivo.get("perfis", {}) if isinstance(competitivo, dict) else {}
        perfil_competitivo = competitivos.get(str(user_id), {}) if isinstance(competitivos, dict) else {}
        if isinstance(perfil_competitivo, dict) and perfil_competitivo:
            perfil = {
                chave: perfil_competitivo[chave]
                for chave in PADRAO_PERFIL
                if chave in perfil_competitivo
            }

    return _normalizar_perfil(perfil)


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


async def _atualizar_ranking_competitivo(
    user_id: int,
    perfil: dict,
    nome: str = "",
    delta_pontos: int = 0,
    evento_id: str = "",
) -> dict:
    """
    Atualiza o ranking competitivo privado do próprio bot.

    Os dados ficam no namespace exclusivo NÊMESIS do armazenamento. Esta
    função não faz chamadas nem sincronizações com o site.
    """

    competitivo = await somar_pontos_competitivo(
        user_id=user_id,
        nome=nome,
        delta=delta_pontos,
        vitorias=perfil.get(
            "vitorias",
            0,
        ),
        derrotas=perfil.get(
            "derrotas",
            0,
        ),
        evento_id=evento_id,
    )

    competitivo["xp"] = int(
        perfil.get(
            "xp",
            0,
        )
        or 0
    )

    competitivo["kills"] = int(
        perfil.get(
            "kills",
            0,
        )
        or 0
    )

    competitivo["deaths"] = int(
        perfil.get(
            "deaths",
            0,
        )
        or 0
    )

    competitivo["mvps"] = int(
        perfil.get(
            "mvps",
            0,
        )
        or 0
    )

    competitivo["sequencia_atual"] = int(
        perfil.get(
            "sequencia_atual",
            0,
        )
        or 0
    )

    competitivo["maior_sequencia"] = int(
        perfil.get(
            "maior_sequencia",
            0,
        )
        or 0
    )

    competitivo["patente"] = perfil.get(
        "patente"
    )

    competitivo["medalhas"] = list(
        perfil.get(
            "medalhas",
            [],
        )
    )

    kills = int(
        perfil.get(
            "kills",
            0,
        )
        or 0
    )

    deaths = int(
        perfil.get(
            "deaths",
            0,
        )
        or 0
    )

    competitivo["kdr"] = (
        round(
            kills / deaths,
            2,
        )
        if deaths > 0
        else float(kills)
    )

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        {
            "catalogo": [],
            "perfis": {},
        },
    )

    dados.setdefault(
        "catalogo",
        [],
    )

    dados.setdefault(
        "perfis",
        {},
    )

    dados["perfis"][
        str(user_id)
    ] = competitivo

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )

    return competitivo


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

    await _salvar_perfil(
        guild_id,
        user_id,
        perfil,
    )

    delta_pontos = (
        (
            XP_VITORIA
            if venceu
            else XP_DERROTA
        )
        + (
            10
            if venceu
            else 0
        )
        + (
            XP_BONUS_MVP
            if foi_mvp
            else 0
        )
    )

    competitivo = await _atualizar_ranking_competitivo(
        user_id=user_id,
        perfil=perfil,
        delta_pontos=delta_pontos,
    )

    return {
        "perfil": perfil,
        "competitivo": competitivo,
        "medalhas_novas": medalhas_novas,
        "patente_antiga": patente_antiga,
    }


async def registrar_empate_guerra(
    guild_id: int,
    user_id: int,
    foi_mvp: bool = False,
) -> dict:
    """Registra empate sem contabilizar vitória ou derrota."""
    perfil = await get_perfil(guild_id, user_id)
    patente_antiga = perfil["patente"]
    perfil["empates"] = int(perfil.get("empates", 0) or 0) + 1
    perfil["sequencia_atual"] = 0
    perfil["xp"] += 15

    if foi_mvp:
        perfil["mvps"] += 1
        perfil["xp"] += XP_BONUS_MVP

    medalhas_novas = _checar_novas_medalhas(perfil)
    perfil["medalhas"].extend(medalhas_novas)
    await _salvar_perfil(guild_id, user_id, perfil)

    delta_pontos = 15 + (XP_BONUS_MVP if foi_mvp else 0)
    competitivo = await _atualizar_ranking_competitivo(
        user_id=user_id,
        perfil=perfil,
        delta_pontos=delta_pontos,
    )
    return {
        "perfil": perfil,
        "competitivo": competitivo,
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

    await _atualizar_ranking_competitivo(
        user_id=vencedor_id,
        perfil=perfil_vencedor,
        delta_pontos=0,
    )

    await _atualizar_ranking_competitivo(
        user_id=perdedor_id,
        perfil=perfil_perdedor,
        delta_pontos=0,
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

    await _atualizar_ranking_competitivo(
        user_id=user_id,
        perfil=perfil,
        delta_pontos=0,
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