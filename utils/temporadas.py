import time
from utils.storage import carregar, salvar
from utils.guild_config import get_config
from utils.perfis import ARQUIVO_PERFIS, get_perfil, _salvar_perfil

ARQUIVO_TEMPORADAS = "temporadas.json"  # { guild_id: {estado} }

PESOS_PADRAO = {"xp": 1, "vitoria": 10, "mvp": 20}
ESTADO_PADRAO = {
    "numero_atual": 1,
    "inicio_timestamp": None,
    "duracao_dias": 30,
    "baseline": {},       # user_id -> pontuação no início da temporada
    "canal_id": None,
    "cargo_campeao_id": None,
    "bonus_ouro": 200,
    "bonus_prata": 100,
    "bonus_bronze": 50,
    "historico": [],
}


async def _tudo():
    return await carregar(ARQUIVO_TEMPORADAS, {})


async def get_estado(guild_id: int) -> dict:
    dados = await _tudo()
    estado = dados.get(str(guild_id), {})
    return {**ESTADO_PADRAO, **estado}


async def _salvar_estado(guild_id: int, estado: dict):
    dados = await _tudo()
    dados[str(guild_id)] = estado
    await salvar(ARQUIVO_TEMPORADAS, dados)


async def _pesos(guild_id: int) -> dict:
    config = await get_config(guild_id)
    return {
        "xp": config.get("peso_ranking_xp", PESOS_PADRAO["xp"]),
        "vitoria": config.get("peso_ranking_vitoria", PESOS_PADRAO["vitoria"]),
        "mvp": config.get("peso_ranking_mvp", PESOS_PADRAO["mvp"]),
    }


def _pontuacao(perfil: dict, pesos: dict) -> float:
    return (perfil.get("xp", 0) * pesos["xp"]
            + perfil.get("vitorias", 0) * pesos["vitoria"]
            + perfil.get("mvps", 0) * pesos["mvp"])


async def _pontuacoes_atuais(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO_PERFIS, {})
    perfis_guild = todos.get(str(guild_id), {})
    pesos = await _pesos(guild_id)
    return {uid: _pontuacao(perfil, pesos) for uid, perfil in perfis_guild.items()}


async def configurar(guild_id: int, **campos):
    estado = await get_estado(guild_id)
    estado.update({k: v for k, v in campos.items() if v is not None})
    if estado["inicio_timestamp"] is None:
        estado["inicio_timestamp"] = time.time()
        estado["baseline"] = await _pontuacoes_atuais(guild_id)
    await _salvar_estado(guild_id, estado)
    return estado


async def top_da_temporada(guild_id: int, limite: int = 10) -> list:
    """Ranking pela pontuação GANHA durante a temporada (delta desde o
    início), não pelo total histórico acumulado do jogador."""
    estado = await get_estado(guild_id)
    atuais = await _pontuacoes_atuais(guild_id)
    deltas = [(uid, pontos - estado["baseline"].get(uid, 0)) for uid, pontos in atuais.items()]
    deltas = [d for d in deltas if d[1] > 0]
    return sorted(deltas, key=lambda x: x[1], reverse=True)[:limite]


async def tempo_restante_segundos(guild_id: int) -> float:
    estado = await get_estado(guild_id)
    if estado["inicio_timestamp"] is None:
        return 0
    fim = estado["inicio_timestamp"] + estado["duracao_dias"] * 86400
    return max(0, fim - time.time())


async def encerrar_temporada(guild_id: int) -> dict:
    """Fecha a temporada: pega o Top 3 pela pontuação ganha na temporada, dá
    o bônus de XP de cada posição, registra no histórico e já inicia a
    próxima temporada com uma nova baseline — sem apagar o progresso geral
    de ninguém (o XP total e as patentes continuam intactos)."""
    estado = await get_estado(guild_id)
    top3 = await top_da_temporada(guild_id, limite=3)

    bonus = [estado["bonus_ouro"], estado["bonus_prata"], estado["bonus_bronze"]]
    vencedores = []
    for i, (uid, pontos) in enumerate(top3):
        user_id = int(uid)
        perfil = await get_perfil(guild_id, user_id)
        perfil["xp"] += bonus[i]
        await _salvar_perfil(guild_id, user_id, perfil)
        vencedores.append({"user_id": user_id, "pontos": pontos, "bonus_xp": bonus[i], "posicao": i + 1})

    estado["historico"].append({
        "numero": estado["numero_atual"],
        "vencedores": vencedores,
        "encerrada_em": time.time(),
    })
    estado["numero_atual"] += 1
    estado["inicio_timestamp"] = time.time()
    estado["baseline"] = await _pontuacoes_atuais(guild_id)
    await _salvar_estado(guild_id, estado)

    return {"numero_encerrada": estado["numero_atual"] - 1, "vencedores": vencedores}