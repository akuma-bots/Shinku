import discord
from utils.guild_config import get_config


async def registrar(guild: discord.Guild, titulo: str, descricao: str, cor: int = 0x99AAB5):
    config = await get_config(guild.id)
    canal_id = config.get("canal_auditoria_id")
    if not canal_id:
        return
    canal = guild.get_channel(canal_id)
    if not canal:
        return
    embed = discord.Embed(title=titulo, description=descricao, color=cor)
    try:
        await canal.send(embed=embed)
    except discord.Forbidden:
        pass