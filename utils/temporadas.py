import asyncio
import time

from utils.storage import carregar, salvar
from utils.guild_config import get_config
from utils.perfis import (
    ARQUIVO_PERFIS,
    get_perfil,
    _salvar_perfil,
)


ARQUIVO_TEMPORADAS = "temporadas.json"
ARQUIVO_COMPETITIVO = "competitivo.json"


PESOS_PADRAO = {
    "xp": 1,
    "vitoria": 10,
    "mvp": 20,
}


ESTADO_PADRAO = {
    "numero_atual": 1,
    "inicio_timestamp": None,
    "duracao_dias": 30,
    "baseline": {},
    "canal_id": None,
    "cargo_campeao_id": None,
    "bonus_ouro": 200,
    "bonus_prata": 100,
    "bonus_bronze": 50,
    "historico": [],
}


async def _tudo():
    return await carregar(
        ARQUIVO_TEMPORADAS,
        {},
    )


async def get_estado(
    guild_id: int,
) -> dict:

    dados = await _tudo()

    estado = dados.get(
        str(guild_id),
        {},
    )

    return {
        **ESTADO_PADRAO,
        **estado,
    }


async def _salvar_estado(
    guild_id: int,
    estado: dict,
):

    dados = await _tudo()

    dados[str(guild_id)] = estado

    await salvar(
        ARQUIVO_TEMPORADAS,
        dados,
    )


async def _pesos(
    guild_id: int,
) -> dict:

    config = await get_config(
        guild_id
    )

    return {
        "xp": config.get(
            "peso_ranking_xp",
            PESOS_PADRAO["xp"],
        ),

        "vitoria": config.get(
            "peso_ranking_vitoria",
            PESOS_PADRAO["vitoria"],
        ),

        "mvp": config.get(
            "peso_ranking_mvp",
            PESOS_PADRAO["mvp"],
        ),
    }


def _pontuacao(
    perfil: dict,
    pesos: dict,
) -> float:

    return (
        perfil.get(
            "xp",
            0,
        )
        * pesos["xp"]
        + perfil.get(
            "vitorias",
            0,
        )
        * pesos["vitoria"]
        + perfil.get(
            "mvps",
            0,
        )
        * pesos["mvp"]
    )


async def _pontuacoes_atuais(
    guild_id: int,
) -> dict:

    todos = await carregar(
        ARQUIVO_PERFIS,
        {},
    )

    perfis_guild = todos.get(
        str(guild_id),
        {},
    )

    pesos = await _pesos(
        guild_id
    )

    return {
        uid: _pontuacao(
            perfil,
            pesos,
        )
        for uid, perfil
        in perfis_guild.items()
    }


async def configurar(
    guild_id: int,
    **campos,
):

    estado = await get_estado(
        guild_id
    )

    estado.update(
        {
            chave: valor
            for chave, valor
            in campos.items()
            if valor is not None
        }
    )

    if (
        estado["inicio_timestamp"]
        is None
    ):

        estado["inicio_timestamp"] = (
            time.time()
        )

        estado["baseline"] = (
            await _pontuacoes_atuais(
                guild_id
            )
        )

    await _salvar_estado(
        guild_id,
        estado,
    )

    return estado


async def top_da_temporada(
    guild_id: int,
    limite: int = 10,
) -> list:

    estado = await get_estado(
        guild_id
    )

    atuais = await _pontuacoes_atuais(
        guild_id
    )

    deltas = [
        (
            uid,
            pontos
            - estado["baseline"].get(
                uid,
                0,
            ),
        )
        for uid, pontos
        in atuais.items()
    ]

    deltas = [
        item
        for item in deltas
        if item[1] > 0
    ]

    return sorted(
        deltas,
        key=lambda item: item[1],
        reverse=True,
    )[:limite]


async def tempo_restante_segundos(
    guild_id: int,
) -> float:

    estado = await get_estado(
        guild_id
    )

    if (
        estado["inicio_timestamp"]
        is None
    ):
        return 0

    fim = (
        estado["inicio_timestamp"]
        + estado["duracao_dias"] * 86400
    )

    return max(
        0,
        fim - time.time(),
    )


async def _sincronizar_perfil_site(
    user_id: int,
    perfil: dict,
):
    """
    Atualiza o perfil competitivo compartilhado
    pelo Dashboard sem alterar a pontuação ou o Elo existentes.
    """

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

    chave = str(user_id)

    competitivo = dados["perfis"].get(
        chave,
        {
            "discordId": chave,
            "nome": "",
            "pontos": 0,
            "elo": 1000,
            "vitorias": 0,
            "derrotas": 0,
        },
    )

    competitivo["discordId"] = chave

    competitivo["xp"] = int(
        perfil.get(
            "xp",
            0,
        )
        or 0
    )

    competitivo["vitorias"] = int(
        perfil.get(
            "vitorias",
            0,
        )
        or 0
    )

    competitivo["derrotas"] = int(
        perfil.get(
            "derrotas",
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

    mortes = int(
        perfil.get(
            "deaths",
            0,
        )
        or 0
    )

    kills = int(
        perfil.get(
            "kills",
            0,
        )
        or 0
    )

    competitivo["kdr"] = (
        round(
            kills / mortes,
            2,
        )
        if mortes > 0
        else float(kills)
    )

    dados["perfis"][chave] = (
        competitivo
    )

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )


_ENCERRAR_TEMPORADA_LOCK = asyncio.Lock()


async def encerrar_temporada(
    guild_id: int,
) -> dict:
    """Encerra uma temporada com recuperação segura e sem bônus duplicados."""
    async with _ENCERRAR_TEMPORADA_LOCK:
        estado = await get_estado(guild_id)
        pendente = estado.get("encerramento_pendente")

        # Guarda o Top 3 antes de alterar perfis. Se uma gravação ou a
        # sincronização com o site falhar, a próxima execução retoma a mesma
        # temporada e os mesmos vencedores, sem recalcular o ranking alterado.
        if not isinstance(pendente, dict):
            top3 = await top_da_temporada(guild_id, limite=3)
            bonus = [
                int(estado.get("bonus_ouro", 200) or 0),
                int(estado.get("bonus_prata", 100) or 0),
                int(estado.get("bonus_bronze", 50) or 0),
            ]
            vencedores = [
                {
                    "user_id": int(uid),
                    "pontos": pontos,
                    "bonus_xp": bonus[i],
                    "posicao": i + 1,
                }
                for i, (uid, pontos) in enumerate(top3)
            ]
            pendente = {
                "numero": int(estado.get("numero_atual", 1) or 1),
                "vencedores": vencedores,
                "iniciado_em": time.time(),
            }
            estado["encerramento_pendente"] = pendente
            await _salvar_estado(guild_id, estado)

        numero = int(pendente.get("numero", estado.get("numero_atual", 1)) or 1)
        vencedores = pendente.get("vencedores", [])
        if not isinstance(vencedores, list):
            raise ValueError("O registro de encerramento da temporada está inválido.")

        evento_id = f"temporada:{guild_id}:{numero}:bonus_xp"
        for vencedor in vencedores:
            if not isinstance(vencedor, dict):
                continue
            user_id = int(vencedor["user_id"])
            bonus_xp = max(0, int(vencedor.get("bonus_xp", 0) or 0))
            perfil = await get_perfil(guild_id, user_id)
            eventos = perfil.get("temporadas_bonus_aplicados", [])
            if not isinstance(eventos, list):
                eventos = []

            if evento_id not in eventos:
                perfil["xp"] = int(perfil.get("xp", 0) or 0) + bonus_xp
                eventos.append(evento_id)
                perfil["temporadas_bonus_aplicados"] = eventos[-500:]
                await _salvar_perfil(guild_id, user_id, perfil)

            # Mesmo se o XP já tiver sido persistido antes de uma falha,
            # tenta novamente a sincronização sem repetir o bônus.
            await _sincronizar_perfil_site(user_id, perfil)

        historico = estado.get("historico", [])
        if not isinstance(historico, list):
            historico = []
        if not any(
            isinstance(item, dict) and int(item.get("numero", -1)) == numero
            for item in historico
        ):
            historico.append({
                "numero": numero,
                "vencedores": vencedores,
                "encerrada_em": time.time(),
            })

        estado["historico"] = historico
        estado["numero_atual"] = max(
            int(estado.get("numero_atual", 1) or 1),
            numero + 1,
        )
        estado["inicio_timestamp"] = time.time()
        estado["baseline"] = await _pontuacoes_atuais(guild_id)
        estado.pop("encerramento_pendente", None)
        await _salvar_estado(guild_id, estado)

        return {
            "numero_encerrada": numero,
            "vencedores": vencedores,
        }


async def sincronizar_todos_site(
    guild_id: int,
) -> int:
    """
    Sincroniza todos os perfis envolvidos
    no ranking de temporadas com o Dashboard.
    """

    todos = await carregar(
        ARQUIVO_PERFIS,
        {},
    )

    perfis = todos.get(
        str(guild_id),
        {},
    )

    quantidade = 0

    for user_id, perfil in perfis.items():

        if not isinstance(
            perfil,
            dict,
        ):
            continue

        try:

            await _sincronizar_perfil_site(
                int(user_id),
                perfil,
            )

            quantidade += 1

        except Exception as erro:

            print(
                "[TEMPORADAS] "
                f"Falha ao sincronizar "
                f"{user_id}: {erro}"
            )

    return quantidade