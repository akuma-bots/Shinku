from utils.storage import carregar, salvar

ARQUIVO_CATEGORIAS = "ajuda_categorias.json"  # { guild_id: { comando: categoria } }


async def get_categoria_salva(guild_id: int, comando: str):
    """Devolve a categoria escolhida manualmente pro comando, ou None se
    ninguém configurou (nesse caso, o cog decide automaticamente)."""
    dados = await carregar(ARQUIVO_CATEGORIAS, {})
    return dados.get(str(guild_id), {}).get(comando)


async def definir_categoria(guild_id: int, comando: str, categoria: str):
    dados = await carregar(ARQUIVO_CATEGORIAS, {})
    guild_dados = dados.setdefault(str(guild_id), {})
    guild_dados[comando] = categoria
    await salvar(ARQUIVO_CATEGORIAS, dados)