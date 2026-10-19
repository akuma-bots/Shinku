import asyncio
import time
import uuid

from utils.storage import carregar, salvar


ARQUIVO_MISSOES = "missoes.json"
_MISSOES_LOCK = asyncio.Lock()


PADRAO = {
    "guilds": {}
}


TIPOS_VALIDOS = {
    "missao",
    "contribuicao",
    "especial",
}


def _normalizar_tipo(tipo: str) -> str:
    valor = str(tipo or "").strip().lower()

    if valor in ("missao", "missões", "missoes", "pvp"):
        return "missao"

    if valor in (
        "contribuicao",
        "contribuição",
        "pve",
        "contribuicoes",
        "contribuições",
        "pontuacao",
        "pontuação",
        "pontuacoes",
        "pontuações",
    ):
        return "contribuicao"

    if valor in (
        "especial",
        "missao_especial",
        "missão_especial",
        "missoes_especiais",
        "missões_especiais",
    ):
        return "especial"

    return valor


def _normalizar_missao(missao: dict) -> dict:
    if not isinstance(missao, dict):
        return {}

    tipo = _normalizar_tipo(missao.get("tipo"))

    recompensa = missao.get(
        "recompensa_xp",
        missao.get("pontos", 0),
    )

    try:
        recompensa = int(recompensa or 0)
    except (TypeError, ValueError, OverflowError):
        recompensa = 0
    # Recompensas negativas em dados legados nunca devem virar débito de XP.
    recompensa = max(0, recompensa)

    return {
        **missao,
        "id": str(
            missao.get("id")
            or uuid.uuid4().hex[:8]
        ),
        "tipo": tipo,
        "titulo": str(
            missao.get("titulo")
            or missao.get("nome")
            or "Atividade sem título"
        ),
        "descricao": str(
            missao.get("descricao")
            or ""
        ),
        "recompensa_xp": recompensa,
        "pontos": recompensa,
        "criado_por": missao.get(
            "criado_por",
            missao.get("criadoPor"),
        ),
        "origem": missao.get(
            "origem",
            "lider",
        ),
        "ativa": missao.get(
            "ativa",
            True,
        ) is not False,
        "timestamp": missao.get(
            "timestamp",
            missao.get(
                "criadoEm",
                time.time(),
            ),
        ),
    }


async def _tudo():
    dados = await carregar(
        ARQUIVO_MISSOES,
        PADRAO.copy(),
    )

    if not isinstance(dados, dict):
        dados = {}

    """
    Compatibilidade com o formato antigo do Bot:

    {
        "guild_id": [
            {...}
        ]
    }

    Converte para:

    {
        "guilds": {
            "guild_id": {
                "missoes": [...],
                "submissoes": [...]
            }
        }
    }
    """

    if "guilds" not in dados:
        guilds = {}

        for chave, valor in dados.items():
            if not isinstance(valor, list):
                continue

            guilds[str(chave)] = {
                "missoes": [
                    _normalizar_missao(m)
                    for m in valor
                    if isinstance(m, dict)
                ],
                "submissoes": [],
            }

        dados = {
            "guilds": guilds,
        }

        await salvar(
            ARQUIVO_MISSOES,
            dados,
        )

    if not isinstance(dados.get("guilds"), dict):
        dados["guilds"] = {}

    return dados


async def _guild(guild_id: int) -> dict:
    dados = await _tudo()

    chave = str(guild_id)

    guild = dados["guilds"].get(chave)

    if not isinstance(guild, dict):
        guild = {
            "missoes": [],
            "submissoes": [],
        }

    missoes = guild.get("missoes", [])
    submissoes = guild.get("submissoes", [])
    if not isinstance(missoes, list):
        missoes = []
    if not isinstance(submissoes, list):
        submissoes = []

    guild["missoes"] = [
        _normalizar_missao(m)
        for m in missoes
        if isinstance(m, dict)
    ]
    guild["submissoes"] = [
        submissao for submissao in submissoes
        if isinstance(submissao, dict)
    ]

    return guild


async def _salvar_guild(
    guild_id: int,
    guild_data: dict,
):
    dados = await _tudo()

    dados["guilds"][str(guild_id)] = guild_data

    await salvar(
        ARQUIVO_MISSOES,
        dados,
    )


async def listar(
    guild_id: int,
    tipo: str = None,
    origem: str = None,
    apenas_ativas: bool = True,
) -> list:
    guild = await _guild(guild_id)

    lista = guild.get(
        "missoes",
        [],
    )

    if tipo:
        tipo = _normalizar_tipo(tipo)

        lista = [
            m
            for m in lista
            if _normalizar_tipo(
                m.get("tipo")
            ) == tipo
        ]

    if origem:
        lista = [
            m
            for m in lista
            if m.get(
                "origem",
                "lider",
            ) == origem
        ]

    if apenas_ativas:
        lista = [
            m
            for m in lista
            if m.get("ativa", True)
        ]

    return lista


async def criar(
    guild_id: int,
    tipo: str,
    titulo: str,
    descricao: str,
    recompensa_xp: int,
    criado_por: int = None,
    origem: str = "lider",
) -> dict:
    tipo = _normalizar_tipo(tipo)

    if tipo not in TIPOS_VALIDOS:
        raise ValueError(
            "Tipo de missão inválido."
        )

    try:
        recompensa_xp = int(recompensa_xp)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError("A recompensa precisa ser um número inteiro válido.") from erro
    if recompensa_xp < 0:
        raise ValueError("A recompensa de XP não pode ser negativa.")

    titulo = str(titulo or "").strip()
    if not titulo:
        raise ValueError("O título da missão não pode ficar vazio.")

    async with _MISSOES_LOCK:
        guild = await _guild(guild_id)

        missao = {
            "id": str(uuid.uuid4())[:8],
            "tipo": tipo,
            "titulo": str(titulo),
            "descricao": str(descricao or ""),
            "recompensa_xp": recompensa_xp,
            "pontos": recompensa_xp,
            "criado_por": criado_por,
            "origem": origem,
            "ativa": True,
            "timestamp": time.time(),
        }

        guild["missoes"].append(missao)
        await _salvar_guild(guild_id, guild)
        return missao


async def get(
    guild_id: int,
    missao_id: str,
):
    guild = await _guild(guild_id)

    return next(
        (
            m
            for m in guild.get(
                "missoes",
                [],
            )
            if str(m.get("id"))
            == str(missao_id)
        ),
        None,
    )


async def desativar(
    guild_id: int,
    missao_id: str,
) -> bool:
    async with _MISSOES_LOCK:
        guild = await _guild(guild_id)
        alvo = next(
            (m for m in guild.get("missoes", []) if str(m.get("id")) == str(missao_id)),
            None,
        )
        if not alvo:
            return False
        alvo["ativa"] = False
        await _salvar_guild(guild_id, guild)
        return True


async def desativar_todas_por_origem(
    guild_id: int,
    origem: str,
):
    async with _MISSOES_LOCK:
        guild = await _guild(guild_id)
        for missao in guild.get("missoes", []):
            if missao.get("origem", "lider") == origem and missao.get("ativa", True):
                missao["ativa"] = False
        await _salvar_guild(guild_id, guild)


async def listar_submissoes(
    guild_id: int,
    status: str = None,
) -> list:
    guild = await _guild(guild_id)

    lista = guild.get("submissoes", [])
    if not isinstance(lista, list):
        return []
    lista = [submissao for submissao in lista if isinstance(submissao, dict)]
    if status:
        lista = [submissao for submissao in lista if submissao.get("status") == status]
    return lista


async def salvar_submissoes(
    guild_id: int,
    submissoes: list,
):
    async with _MISSOES_LOCK:
        guild = await _guild(guild_id)
        guild["submissoes"] = [
            submissao for submissao in submissoes
            if isinstance(submissao, dict)
        ] if isinstance(submissoes, list) else []
        await _salvar_guild(guild_id, guild)