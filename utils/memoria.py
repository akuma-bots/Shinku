import time
from utils.storage import carregar, salvar

ARQUIVO_INTERACOES = "memoria_interacoes.json"   # { guild_id: [ {pergunta, resposta, timestamp} ] }
ARQUIVO_FATOS = "fatos_ensinados.json"            # { guild_id: [ {fato, ensinado_por_id, timestamp} ] }

MAX_INTERACOES_GUARDADAS = 30
MAX_INTERACOES_NO_CONTEXTO = 8


async def salvar_interacao(guild_id: int, pergunta: str, resposta: str):
    todos = await carregar(ARQUIVO_INTERACOES, {})
    lista = todos.setdefault(str(guild_id), [])
    lista.append({"pergunta": pergunta[:300], "resposta": resposta[:500], "timestamp": time.time()})
    todos[str(guild_id)] = lista[-MAX_INTERACOES_GUARDADAS:]  # não deixa crescer pra sempre
    await salvar(ARQUIVO_INTERACOES, todos)


async def resumo_interacoes_recentes(guild_id: int) -> str:
    todos = await carregar(ARQUIVO_INTERACOES, {})
    lista = todos.get(str(guild_id), [])[-MAX_INTERACOES_NO_CONTEXTO:]
    if not lista:
        return "(nenhuma conversa recente registrada ainda)"
    return "\n".join(f"- Perguntaram: \"{i['pergunta']}\" → Você respondeu: \"{i['resposta']}\"" for i in lista)


async def ensinar_fato(guild_id: int, fato: str, ensinado_por_id: int):
    todos = await carregar(ARQUIVO_FATOS, {})
    lista = todos.setdefault(str(guild_id), [])
    lista.append({"fato": fato, "ensinado_por_id": ensinado_por_id, "timestamp": time.time()})
    todos[str(guild_id)] = lista
    await salvar(ARQUIVO_FATOS, todos)


async def listar_fatos(guild_id: int) -> list:
    todos = await carregar(ARQUIVO_FATOS, {})
    return todos.get(str(guild_id), [])


async def esquecer_fato(guild_id: int, indice: int) -> bool:
    todos = await carregar(ARQUIVO_FATOS, {})
    lista = todos.get(str(guild_id), [])
    if 0 <= indice < len(lista):
        lista.pop(indice)
        todos[str(guild_id)] = lista
        await salvar(ARQUIVO_FATOS, todos)
        return True
    return False


async def resumo_fatos_ensinados(guild_id: int) -> str:
    lista = await listar_fatos(guild_id)
    if not lista:
        return "(nenhum fato ensinado pela equipe ainda)"
    return "\n".join(f"- {f['fato']}" for f in lista)
