import discord
from discord import app_commands
from discord.ext import commands

from utils import ajuda

CATEGORIA_CHOICES = [
    app_commands.Choice(name="Membros", value="membros"),
    app_commands.Choice(name="Staff", value="staff"),
    app_commands.Choice(name="Donos", value="donos"),
]

NOMES_CATEGORIA = {"membros": "👤 Comandos de Membros", "staff": "🛠️ Comandos de Staff", "donos": "👑 Comandos de Donos"}
ORDEM_CATEGORIA = ["membros", "staff", "donos"]


class Ajuda(commands.Cog):
    """/help com todos os comandos do bot organizados em 3 categorias.
    Por padrão: um comando sem nenhuma permissão exigida cai em "Membros";
    um comando que exige alguma permissão (administrator, manage_guild, etc)
    cai em "Staff" automaticamente. "Donos" começa vazio — use
    /ajuda-categorizar pra mover manualmente os comandos mais sensíveis pra
    lá, sem precisar mexer em código."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _categoria_do_comando(self, guild_id: int, comando: app_commands.Command) -> str:
        salvo = await ajuda.get_categoria_salva(guild_id, comando.qualified_name)
        if salvo:
            return salvo
        return "staff" if comando.checks else "membros"

    async def _montar_agrupado(self, guild_id: int) -> dict:
        agrupado = {"membros": [], "staff": [], "donos": []}
        for comando in sorted(self.bot.tree.get_commands(), key=lambda c: c.name):
            if not isinstance(comando, app_commands.Command):
                continue
            categoria = await self._categoria_do_comando(guild_id, comando)
            agrupado.setdefault(categoria, []).append(comando)
        return agrupado

    @app_commands.command(name="help", description="Lista todos os comandos do bot, por categoria.")
    async def help_cmd(self, interaction: discord.Interaction):
        agrupado = await self._montar_agrupado(interaction.guild.id)
        eh_administrador = interaction.user.guild_permissions.administrator
        eh_dono_servidor = interaction.user.id == interaction.guild.owner_id

        embed = discord.Embed(title="📖 Comandos do bot", color=0x5865F2)
        for categoria in ORDEM_CATEGORIA:
            comandos = agrupado.get(categoria, [])
            if not comandos:
                continue
            if categoria == "staff" and not (eh_administrador or interaction.user.guild_permissions.manage_guild):
                continue
            if categoria == "donos" and not (eh_administrador or eh_dono_servidor):
                continue

            linhas = [f"`/{c.name}` — {c.description}" for c in comandos]
            bloco, primeiro = "", True
            for linha in linhas:
                if len(bloco) + len(linha) + 1 > 1024:
                    embed.add_field(name=NOMES_CATEGORIA[categoria] if primeiro else "↳ continuação", value=bloco, inline=False)
                    bloco, primeiro = "", False
                bloco += linha + "\n"
            if bloco:
                embed.add_field(name=NOMES_CATEGORIA[categoria] if primeiro else "↳ continuação", value=bloco, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ajuda-categorizar", description="Move um comando pra outra categoria no /help.")
    @app_commands.describe(comando="Nome do comando (sem a barra)", categoria="Nova categoria")
    @app_commands.choices(categoria=CATEGORIA_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def ajuda_categorizar(self, interaction: discord.Interaction, comando: str, categoria: app_commands.Choice[str]):
        if not self.bot.tree.get_command(comando):
            await interaction.response.send_message(f"Não achei nenhum comando chamado `{comando}`.", ephemeral=True)
            return
        await ajuda.definir_categoria(interaction.guild.id, comando, categoria.value)
        await interaction.response.send_message(f"✅ `/{comando}` agora aparece em **{NOMES_CATEGORIA[categoria.value]}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ajuda(bot))