from utils.storage import carregar, salvar

ARQUIVO_RECORDES = "recordes.json"  # { guild_id: { categoria: {"user_id":.., "valor":..} } }


async def _tudo():
    return await carregar(ARQUIVO_RECORDES, {})


async def obter_todos(guild_id: int) -> dict:
    dados = await _tudo()
    return dados.get(str(guild_id), {})


async def verificar_e_atualizar(guild_id: int, categoria: str, user_id: int, valor: float):
    """Se `valor` bater o recorde atual da categoria (ou for o primeiro),
    atualiza e retorna o novo recorde. Senão, retorna None."""
    dados = await _tudo()
    recordes_guild = dados.setdefault(str(guild_id), {})
    atual = recordes_guild.get(categoria)
    if atual and valor <= atual["valor"]:
        return None
    novo = {"user_id": user_id, "valor": valor}
    recordes_guild[categoria] = novo
    await salvar(ARQUIVO_RECORDES, dados)
    return novo