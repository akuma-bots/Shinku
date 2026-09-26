import discord
from discord import app_commands
from discord.ext import commands

SISTEMAS = {
    "Missoes": ("🎯", "Missões"),
    "Desafios": ("⚔️", "PvP / Desafios"),
    "PvE": ("👹", "PvE"),
    "Guerras": ("🏰", "Guerras"),
    "Perfil": ("🎖️", "Perfil & Patentes"),
    "PerfilCard": ("🖼️", "Perfil Visual"),
    "RankingGeral": ("🌍", "Ranking Geral"),
    "PontuacaoPvE": ("🗡️", "Pontuação PvE"),
    "Recordes": ("🏅", "Recordes"),
    "Temporadas": ("🏁", "Temporadas"),
    "Gangues": ("🏴", "Gangues"),
    "Loja": ("🛒", "Loja"),
    "Tickets": ("🎫", "Tickets"),
    "Formularios": ("📝", "Formulários"),
    "Revisoes": ("📋", "Revisão de Provas"),
    "Auditoria": ("🧾", "Auditoria"),
    "Ajuda": ("📖", "Ajuda"),
}
ORDEM = list(SISTEMAS.keys())


def _sistema_do_comando(comando: app_commands.Command):
    cog = comando.binding
    nome_cog = cog.qualified_name if cog else "Outros"
    emoji, titulo = SISTEMAS.get(nome_cog, ("🔧", nome_cog))
    return nome_cog, emoji, titulo


def _pode_ver(comando: app_commands.Command, membro: discord.Member) -> bool:
    """Comando sem nenhuma permissão exigida (`checks` vazio) é visível pra
    todo mundo; comando que exige permissão só aparece pra quem tem
    manage_guild ou administrator — automático, sem precisar marcar nada."""
    if not comando.checks:
        return True
    return membro.guild_permissions.administrator or membro.guild_permissions.manage_guild


class Ajuda(commands.Cog):
    """/help com todos os comandos organizados por SISTEMA (Missões, PvP,
    PvE, Guerras, Tickets, Formulários, etc.) — cada bloco é um cog, e cada
    pessoa só vê, dentro de cada bloco, os comandos que ela tem permissão
    de usar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _montar_agrupado(self, membro: discord.Member) -> dict:
        agrupado = {}
        for comando in sorted(self.bot.tree.get_commands(), key=lambda c: c.name):
            if not isinstance(comando, app_commands.Command):
                continue
            if not _pode_ver(comando, membro):
                continue
            nome_cog, emoji, titulo = _sistema_do_comando(comando)
            agrupado.setdefault(nome_cog, {"emoji": emoji, "titulo": titulo, "comandos": []})
            agrupado[nome_cog]["comandos"].append(comando)
        return agrupado

    @app_commands.command(name="help", description="Lista todos os comandos do bot, organizados por sistema.")
    async def help_cmd(self, interaction: discord.Interaction):
        agrupado = self._montar_agrupado(interaction.user)
        chaves_ordenadas = [k for k in ORDEM if k in agrupado] + [k for k in agrupado if k not in ORDEM]

        embed = discord.Embed(
            title="📖 Comandos do Bot",
            description="Cada sistema tem seu próprio bloco de comandos abaixo.",
            color=0x5865F2,
        )
        for chave in chaves_ordenadas:
            grupo = agrupado[chave]
            linhas = [f"**/{c.name}** — {c.description}" for c in grupo["comandos"]]
            bloco, primeiro = "", True
            for linha in linhas:
                if len(bloco) + len(linha) + 1 > 1024:
                    embed.add_field(name=f"{grupo['emoji']} {grupo['titulo']}" if primeiro else "↳ continuação", value=bloco, inline=False)
                    bloco, primeiro = "", False
                bloco += linha + "\n"
            if bloco:
                embed.add_field(name=f"{grupo['emoji']} {grupo['titulo']}" if primeiro else "↳ continuação", value=bloco, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ajuda(bot))