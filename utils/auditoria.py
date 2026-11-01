import discord

async def registrar(
    guild: discord.Guild,
    titulo: str,
    descricao: str,
    cor: int = 0x99AAB5,
    categoria: str = "administracao",
):
    """Encaminha auditorias para o tópico permanente do Registro Global."""
    from utils.registro_global import registrar as registrar_global
    return await registrar_global(
        guild, categoria, titulo, descricao, cor=cor,
    )
