import time
import uuid
from utils.storage import carregar, salvar

ARQUIVO_FORMULARIOS = "formularios.json"          # { guild_id: [ {formulario...}, ... ] }
ARQUIVO_RESPOSTAS = "formularios_respostas.json"  # { guild_id: [ {resposta...}, ... ] }


async def _tudo_formularios():
    return await carregar(ARQUIVO_FORMULARIOS, {})


async def _salvar_formularios_guild(guild_id: int, lista: list):
    dados = await _tudo_formularios()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_FORMULARIOS, dados)


async def listar_formularios(guild_id: int) -> list:
    dados = await _tudo_formularios()
    return dados.get(str(guild_id), [])


async def get_formulario(guild_id: int, formulario_id: str):
    lista = await listar_formularios(guild_id)
    return next((f for f in lista if f["id"] == formulario_id), None)


async def criar_formulario(guild_id: int, nome: str, titulo_painel: str, descricao_painel: str,
                            banner_url: str, criado_por: int) -> dict:
    lista = await listar_formularios(guild_id)
    formulario = {
        "id": str(uuid.uuid4())[:8],
        "nome": nome,
        "titulo_painel": titulo_painel,
        "descricao_painel": descricao_painel,
        "banner_url": banner_url,
        "paginas": [],                # lista de páginas; cada página é uma lista de até 5 perguntas
        "cargos_notificar": [],       # lista de role_id
        "criado_por": criado_por,
        "timestamp": time.time(),
    }
    lista.append(formulario)
    await _salvar_formularios_guild(guild_id, lista)
    return formulario


async def remover_formulario(guild_id: int, formulario_id: str) -> bool:
    lista = await listar_formularios(guild_id)
    nova_lista = [f for f in lista if f["id"] != formulario_id]
    if len(nova_lista) == len(lista):
        return False
    await _salvar_formularios_guild(guild_id, nova_lista)
    return True


def perguntas_flat(formulario: dict) -> list:
    """Todas as perguntas do formulário, de todas as páginas, em ordem."""
    achatado = []
    for pagina in formulario["paginas"]:
        achatado.extend(pagina)
    return achatado


async def adicionar_pagina(guild_id: int, formulario_id: str, perguntas: list) -> dict:
    lista = await listar_formularios(guild_id)
    alvo = next((f for f in lista if f["id"] == formulario_id), None)
    if not alvo:
        return None
    alvo["paginas"].append(perguntas[:5])
    await _salvar_formularios_guild(guild_id, lista)
    return alvo


async def remover_pagina(guild_id: int, formulario_id: str, indice: int) -> bool:
    lista = await listar_formularios(guild_id)
    alvo = next((f for f in lista if f["id"] == formulario_id), None)
    if not alvo or not (0 <= indice < len(alvo["paginas"])):
        return False
    alvo["paginas"].pop(indice)
    await _salvar_formularios_guild(guild_id, lista)
    return True


async def adicionar_cargo_notificar(guild_id: int, formulario_id: str, cargo_id: int) -> bool:
    lista = await listar_formularios(guild_id)
    alvo = next((f for f in lista if f["id"] == formulario_id), None)
    if not alvo:
        return False
    if cargo_id not in alvo["cargos_notificar"]:
        alvo["cargos_notificar"].append(cargo_id)
    await _salvar_formularios_guild(guild_id, lista)
    return True


async def remover_cargo_notificar(guild_id: int, formulario_id: str, cargo_id: int) -> bool:
    lista = await listar_formularios(guild_id)
    alvo = next((f for f in lista if f["id"] == formulario_id), None)
    if not alvo:
        return False
    alvo["cargos_notificar"] = [c for c in alvo["cargos_notificar"] if c != cargo_id]
    await _salvar_formularios_guild(guild_id, lista)
    return True


# ---------------- Respostas ----------------

async def _tudo_respostas():
    return await carregar(ARQUIVO_RESPOSTAS, {})


async def _salvar_respostas_guild(guild_id: int, lista: list):
    dados = await _tudo_respostas()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO_RESPOSTAS, dados)


async def criar_resposta(guild_id: int, formulario_id: str, autor_id: int, respostas: list) -> dict:
    dados = await _tudo_respostas()
    lista = dados.get(str(guild_id), [])
    resposta = {
        "id": str(uuid.uuid4())[:8],
        "formulario_id": formulario_id,
        "autor_id": autor_id,
        "respostas": respostas,
        "status": "pendente",
        "revisor_id": None,
        "timestamp": time.time(),
    }
    lista.append(resposta)
    await _salvar_respostas_guild(guild_id, lista)
    return resposta


async def get_resposta(guild_id: int, resposta_id: str):
    dados = await _tudo_respostas()
    lista = dados.get(str(guild_id), [])
    return next((r for r in lista if r["id"] == resposta_id), None)


async def definir_status_resposta(guild_id: int, resposta_id: str, status: str, revisor_id: int):
    dados = await _tudo_respostas()
    lista = dados.get(str(guild_id), [])
    alvo = next((r for r in lista if r["id"] == resposta_id), None)
    if alvo:
        alvo["status"] = status
        alvo["revisor_id"] = revisor_id
        await _salvar_respostas_guild(guild_id, lista)
    return alvo