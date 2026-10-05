from utils.storage import carregar, salvar

ARQUIVO_COMPETITIVO = "competitivo.json"

PADRAO_COMPETITIVO = {
    "catalogo": [],
    "perfis": {},
}


async def somar_pontos_competitivo(
    user_id: int,
    nome: str = "",
    delta: int = 0,
    vitorias: int | None = None,
    derrotas: int | None = None,
) -> dict:
    """
    Atualiza o mesmo competitivo.json usado pelo Dashboard da NÊMESIS.

    O delta é somado ao P.C. existente. Assim, alterações feitas
    manualmente pelo Dashboard não são sobrescritas pelo bot.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        PADRAO_COMPETITIVO.copy(),
    )

    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})

    chave = str(user_id)

    perfil = dados["perfis"].get(chave) or {
        "discordId": chave,
        "nome": nome or "",
        "pontos": 0,
        "elo": 1000,
        "vitorias": 0,
        "derrotas": 0,
    }

    perfil["discordId"] = chave

    if nome:
        perfil["nome"] = nome

    perfil["pontos"] = (
        int(perfil.get("pontos", 0) or 0)
        + int(delta)
    )

    if vitorias is not None:
        perfil["vitorias"] = int(vitorias)

    if derrotas is not None:
        perfil["derrotas"] = int(derrotas)

    dados["perfis"][chave] = perfil

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )

    return perfil


async def migrar_perfil_se_necessario(
    user_id: int,
    nome: str,
    perfil_bot: dict,
) -> dict:
    """
    Migra um perfil antigo do perfis.json para competitivo.json
    somente se ele ainda não existir no ranking compartilhado.

    Se o usuário já tiver perfil criado pelo site, nada é sobrescrito.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        PADRAO_COMPETITIVO.copy(),
    )

    dados.setdefault("catalogo", [])
    dados.setdefault("perfis", {})

    chave = str(user_id)

    if chave in dados["perfis"]:
        return dados["perfis"][chave]

    pontos = (
        int(perfil_bot.get("xp", 0) or 0)
        + int(perfil_bot.get("vitorias", 0) or 0) * 10
        + int(perfil_bot.get("mvps", 0) or 0) * 20
    )

    perfil = {
        "discordId": chave,
        "nome": nome or "",
        "pontos": pontos,
        "elo": 1000,
        "vitorias": int(
            perfil_bot.get("vitorias", 0) or 0
        ),
        "derrotas": int(
            perfil_bot.get("derrotas", 0) or 0
        ),
    }

    dados["perfis"][chave] = perfil

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )

    return perfil