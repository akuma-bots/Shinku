import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config

ARQUIVO = "parcerias.json"


async def _todas():
    return await carregar(ARQUIVO, {})


async def _da_guild(guild_id: int):
    dados = await _todas()
    return dados.get(str(guild_id), [])


async def _salvar_da_guild(guild_id: int, lista):
    dados = await _todas()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO, dados)


class Parcerias(commands.Cog):
    """Registro de parcerias com outros servidores: guarda nome, convite e
    descrição, publica um anúncio no canal de parcerias e mantém uma lista
    consultável."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="configurar-canal-parcerias", description="Define onde as parcerias são anunciadas.")
    @app_commands.describe(canal="Canal de texto para os anúncios de parceria")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_parcerias(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_parcerias_id=canal.id)
        await interaction.response.send_message(f"✅ Parcerias agora são anunciadas em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="adicionar-parceria", description="Registra uma parceria com outro servidor e anuncia no canal configurado.")
    @app_commands.describe(
        nome="Nome do servidor parceiro",
        convite="Link de convite do servidor parceiro",
        descricao="Descrição curta da parceria",
        banner="URL de uma imagem/banner (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def adicionar_parceria(
        self,
        interaction: discord.Interaction,
        nome: str,
        convite: str,
        descricao: str,
        banner: str = None,
    ):
        config = await get_config(interaction.guild.id)
        canal_id = config["canal_parcerias_id"]
        canal = interaction.guild.get_channel(canal_id) if canal_id else None
        if not canal:
            await interaction.response.send_message(
                "Configure o canal de parcerias primeiro com `/configurar-canal-parcerias`.", ephemeral=True
            )
            return

        embed = discord.Embed(title=f"🤝 Nova parceria: {nome}", description=descricao, color=0x57F287)
        embed.add_field(name="Convite", value=convite, inline=False)
        if banner:
            embed.set_image(url=banner)
        embed.set_footer(text=f"Parceria registrada por {interaction.user}")

        await canal.send(embed=embed)

        lista = await _da_guild(interaction.guild.id)
        lista.append({"nome": nome, "convite": convite, "descricao": descricao, "banner": banner})
        await _salvar_da_guild(interaction.guild.id, lista)

        await interaction.response.send_message(f"✅ Parceria com **{nome}** registrada e anunciada em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="remover-parceria", description="Remove uma parceria registrada pelo nome.")
    @app_commands.describe(nome="Nome exato da parceria a remover")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remover_parceria(self, interaction: discord.Interaction, nome: str):
        lista = await _da_guild(interaction.guild.id)
        nova_lista = [p for p in lista if p["nome"].lower() != nome.lower()]
        if len(nova_lista) == len(lista):
            await interaction.response.send_message("Não achei nenhuma parceria com esse nome.", ephemeral=True)
            return
        await _salvar_da_guild(interaction.guild.id, nova_lista)
        await interaction.response.send_message(f"🗑️ Parceria com **{nome}** removida.", ephemeral=True)

    @app_commands.command(name="parcerias", description="Lista as parcerias registradas deste servidor.")
    async def parcerias(self, interaction: discord.Interaction):
        lista = await _da_guild(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhuma parceria registrada ainda.", ephemeral=True)
            return
        embed = discord.Embed(title="🤝 Parcerias do servidor", color=0x5865F2)
        for p in lista[:25]:
            embed.add_field(name=p["nome"], value=f"{p['descricao']}\n{p['convite']}", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Parcerias(bot))
