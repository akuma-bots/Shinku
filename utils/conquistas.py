import asyncio
import time

from utils.storage import carregar, salvar

ARQUIVO_CONQUISTAS = "conquistas.json"
_LOCK = asyncio.Lock()

CATALOGO_CONQUISTAS = [
    {"id": "primeiro_passo", "nome": "Primeiro Passo", "icone": "⚔️", "categoria": "Progressão", "campo": "xp", "meta": 1000, "descricao": "Acumule 1.000 XP organizacionais.", "recompensa_xp": 25, "raridade": "Comum"},
    {"id": "em_evolucao", "nome": "Em Evolução", "icone": "🩸", "categoria": "Progressão", "campo": "xp", "meta": 5000, "descricao": "Acumule 5.000 XP organizacionais.", "recompensa_xp": 50, "raridade": "Incomum"},
    {"id": "forca_reconhecida", "nome": "Força Reconhecida", "icone": "👑", "categoria": "Progressão", "campo": "xp", "meta": 15000, "descricao": "Acumule 15.000 XP organizacionais.", "recompensa_xp": 100, "raridade": "Rara"},
    {"id": "presenca_inicial", "nome": "Presença Inicial", "icone": "✦", "categoria": "Participação", "campo": "mensagens", "meta": 10, "descricao": "Registre 10 mensagens válidas.", "recompensa_xp": 15, "raridade": "Comum"},
    {"id": "voz_ativa", "nome": "Voz Ativa", "icone": "📡", "categoria": "Participação", "campo": "mensagens", "meta": 100, "descricao": "Registre 100 mensagens válidas.", "recompensa_xp": 35, "raridade": "Incomum"},
    {"id": "presenca_constante", "nome": "Presença Constante", "icone": "🔥", "categoria": "Participação", "campo": "mensagens", "meta": 500, "descricao": "Registre 500 mensagens válidas.", "recompensa_xp": 75, "raridade": "Rara"},
    {"id": "primeira_missao", "nome": "Primeira Operação", "icone": "🎯", "categoria": "Operações", "campo": "missoes", "meta": 1, "descricao": "Tenha sua primeira missão aprovada.", "recompensa_xp": 25, "raridade": "Comum"},
    {"id": "operador", "nome": "Operador", "icone": "🛡️", "categoria": "Operações", "campo": "missoes", "meta": 10, "descricao": "Conclua 10 missões aprovadas.", "recompensa_xp": 50, "raridade": "Incomum"},
    {"id": "especialista_operacional", "nome": "Especialista Operacional", "icone": "💠", "categoria": "Operações", "campo": "missoes", "meta": 25, "descricao": "Conclua 25 missões aprovadas.", "recompensa_xp": 100, "raridade": "Épica"},
    {"id": "primeira_vitoria", "nome": "Primeira Vitória", "icone": "🥉", "categoria": "Combate", "campo": "vitorias", "meta": 1, "descricao": "Conquiste sua primeira vitória registrada.", "recompensa_xp": 25, "raridade": "Comum"},
    {"id": "combatente", "nome": "Combatente", "icone": "⚔️", "categoria": "Combate", "campo": "vitorias", "meta": 10, "descricao": "Conquiste 10 vitórias registradas.", "recompensa_xp": 60, "raridade": "Incomum"},
    {"id": "lenda_do_combate", "nome": "Lenda do Combate", "icone": "🏆", "categoria": "Combate", "campo": "vitorias", "meta": 25, "descricao": "Conquiste 25 vitórias registradas.", "recompensa_xp": 125, "raridade": "Lendária"},
    {"id": "primeiro_mvp", "nome": "Destaque da Operação", "icone": "⭐", "categoria": "Combate", "campo": "mvps", "meta": 1, "descricao": "Receba seu primeiro reconhecimento de MVP.", "recompensa_xp": 35, "raridade": "Incomum"},
    {"id": "mvp_frequente", "nome": "MVP Frequente", "icone": "🌟", "categoria": "Combate", "campo": "mvps", "meta": 5, "descricao": "Receba 5 reconhecimentos de MVP.", "recompensa_xp": 90, "raridade": "Épica"},
    {"id": "sequencia_imparavel", "nome": "Sequência Imparável", "icone": "🔥", "categoria": "Combate", "campo": "maior_sequencia", "meta": 10, "descricao": "Alcance uma sequência de 10 vitórias.", "recompensa_xp": 100, "raridade": "Épica"},
]

CATALOGO_POR_ID = {item["id"]: item for item in CATALOGO_CONQUISTAS}


def avaliar_conquistas(estatisticas: dict) -> list[dict]:
    """Retorna os marcos atingidos sem alterar o armazenamento."""
    estatisticas = estatisticas if isinstance(estatisticas, dict) else {}
    desbloqueadas = []
    for conquista in CATALOGO_CONQUISTAS:
        try:
            valor = max(0, int(estatisticas.get(conquista["campo"], 0) or 0))
        except (TypeError, ValueError, OverflowError):
            valor = 0
        if valor >= conquista["meta"]:
            desbloqueadas.append(conquista)
    return desbloqueadas


async def registrar_desbloqueios(guild_id: int, user_id: int, estatisticas: dict) -> tuple[list[dict], list[dict]]:
    """Persiste desbloqueios uma única vez e devolve novos e recompensas pendentes."""
    candidatos = avaliar_conquistas(estatisticas)
    async with _LOCK:
        dados = await carregar(ARQUIVO_CONQUISTAS, {})
        if not isinstance(dados, dict):
            dados = {}
        guild = dados.setdefault(str(guild_id), {})
        membros = guild.setdefault("membros", {})
        perfil = membros.setdefault(str(user_id), {"desbloqueadas": {}})
        desbloqueadas = perfil.get("desbloqueadas")
        if not isinstance(desbloqueadas, dict):
            desbloqueadas = {}
            perfil["desbloqueadas"] = desbloqueadas

        novos = []
        for conquista in candidatos:
            identificador = conquista["id"]
            if identificador in desbloqueadas:
                continue
            desbloqueadas[identificador] = {
                "desbloqueada_em": int(time.time()),
                "recompensa_xp": int(conquista["recompensa_xp"]),
                "recompensa_status": "pendente" if conquista["recompensa_xp"] else "concluida",
            }
            novos.append(conquista)

        pendentes = []
        for identificador, registro in desbloqueadas.items():
            conquista = CATALOGO_POR_ID.get(identificador)
            if (
                conquista
                and isinstance(registro, dict)
                and registro.get("recompensa_status") == "pendente"
            ):
                pendentes.append(conquista)

        membros[str(user_id)] = perfil
        await salvar(ARQUIVO_CONQUISTAS, dados)
        return novos, pendentes


async def marcar_recompensa_aplicada(guild_id: int, user_id: int, conquista_id: str) -> bool:
    async with _LOCK:
        dados = await carregar(ARQUIVO_CONQUISTAS, {})
        guild = dados.get(str(guild_id), {}) if isinstance(dados, dict) else {}
        membros = guild.get("membros", {}) if isinstance(guild, dict) else {}
        perfil = membros.get(str(user_id), {}) if isinstance(membros, dict) else {}
        desbloqueadas = perfil.get("desbloqueadas", {}) if isinstance(perfil, dict) else {}
        registro = desbloqueadas.get(conquista_id) if isinstance(desbloqueadas, dict) else None
        if not isinstance(registro, dict):
            return False
        registro["recompensa_status"] = "concluida"
        registro["recompensa_aplicada_em"] = int(time.time())
        await salvar(ARQUIVO_CONQUISTAS, dados)
        return True


async def listar_desbloqueadas(guild_id: int, user_id: int) -> dict:
    dados = await carregar(ARQUIVO_CONQUISTAS, {})
    guild = dados.get(str(guild_id), {}) if isinstance(dados, dict) else {}
    membros = guild.get("membros", {}) if isinstance(guild, dict) else {}
    perfil = membros.get(str(user_id), {}) if isinstance(membros, dict) else {}
    desbloqueadas = perfil.get("desbloqueadas", {}) if isinstance(perfil, dict) else {}
    return {
        identificador: registro
        for identificador, registro in desbloqueadas.items()
        if identificador in CATALOGO_POR_ID and isinstance(registro, dict)
    } if isinstance(desbloqueadas, dict) else {}
