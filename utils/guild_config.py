from utils.storage import carregar, salvar

ARQUIVO = "guild_configs.json"

PADRAO = {
    "support_role_id": None,
    "log_channel_id": None,
    "ticket_category_id": None,
    "canais_liberados": {},          # regra_id -> [channel_id, ...] — exceções por servidor
    "canais_cargo_automatico": {},   # channel_id (str) -> role_id — cargo dado ao postar no canal
    "canal_eventos_id": None,        # onde anunciar eventos agendados do Discord
    "canal_parcerias_id": None,      # onde postar as parcerias registradas
    "contadores": [],                # [{ "tipo": "membros", "canal_id": int, "cargo_id": int|None }]
    "canal_denuncias_id": None,      # onde as denúncias chegam pra equipe revisar
    "categoria_modmail_id": None,    # categoria onde os canais de DM/mod mail são criados
}


async def _tudo():
    return await carregar(ARQUIVO, {})


async def get_config(guild_id: int) -> dict:
    dados = await _tudo()
    config = dados.get(str(guild_id), {})
    resultado = {**PADRAO, **config}
    resultado["canais_liberados"] = config.get("canais_liberados", {})
    resultado["canais_cargo_automatico"] = config.get("canais_cargo_automatico", {})
    resultado["contadores"] = config.get("contadores", [])
    return resultado


async def set_config(guild_id: int, **campos) -> dict:
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    for chave, valor in campos.items():
        if valor is not None:
            atual[chave] = valor
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return atual


async def liberar_canal_para_regra(guild_id: int, regra_id: str, canal_id: int):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    excecoes = atual.setdefault("canais_liberados", {})
    lista = excecoes.setdefault(regra_id, [])
    if canal_id not in lista:
        lista.append(canal_id)
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return lista


async def bloquear_canal_para_regra(guild_id: int, regra_id: str, canal_id: int):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    excecoes = atual.setdefault("canais_liberados", {})
    lista = excecoes.get(regra_id, [])
    if canal_id in lista:
        lista.remove(canal_id)
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return lista


async def canal_liberado_para_regra(guild_id: int, regra_id: str, canal_id: int) -> bool:
    config = await get_config(guild_id)
    return canal_id in config["canais_liberados"].get(regra_id, [])


async def definir_canal_cargo_automatico(guild_id: int, canal_id: int, cargo_id: int):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    mapa = atual.setdefault("canais_cargo_automatico", {})
    mapa[str(canal_id)] = cargo_id
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return mapa


async def remover_canal_cargo_automatico(guild_id: int, canal_id: int):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    mapa = atual.setdefault("canais_cargo_automatico", {})
    mapa.pop(str(canal_id), None)
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return mapa


async def adicionar_contador(guild_id: int, tipo: str, canal_id: int, cargo_id: int = None):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    lista = atual.setdefault("contadores", [])
    lista[:] = [c for c in lista if c["canal_id"] != canal_id]
    lista.append({"tipo": tipo, "canal_id": canal_id, "cargo_id": cargo_id})
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return lista


async def remover_contador(guild_id: int, canal_id: int):
    dados = await _tudo()
    atual = dados.get(str(guild_id), dict(PADRAO))
    lista = atual.setdefault("contadores", [])
    lista[:] = [c for c in lista if c["canal_id"] != canal_id]
    dados[str(guild_id)] = atual
    await salvar(ARQUIVO, dados)
    return lista
