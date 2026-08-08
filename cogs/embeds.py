import discord
from discord import app_commands
from discord.ext import commands


def _cor_para_int(valor: str) -> int:
    valor = (valor or "").strip().lstrip("#")
    try:
        return int(valor, 16) if valor else 0x5865F2
    except ValueError:
        return 0x5865F2


class EmbedModal(discord.ui.Modal, title="Criar embed"):
    titulo = discord.ui.TextInput(label="Título", required=False, max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    cor = discord.ui.TextInput(label="Cor em hex (ex: FF0000)", required=False, max_length=7, placeholder="5865F2")
    imagem = discord.ui.TextInput(label="URL da imagem (opcional)", required=False)
    rodape = discord.ui.TextInput(label="Rodapé (opcional)", required=False, max_length=256)

    def __init__(self, canal: discord.TextChannel):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.titulo.value or None,
            description=self.descricao.value or None,
            color=_cor_para_int(self.cor.value),
        )
        if self.imagem.value:
            embed.set_image(url=self.imagem.value)
        if self.rodape.value:
            embed.set_footer(text=self.rodape.value)

        await self.canal.send(embed=embed)
        await interaction.response.send_message(f"✅ Embed enviada em {self.canal.mention}.", ephemeral=True)


class EditarEmbedModal(discord.ui.Modal, title="Editar embed"):
    titulo = discord.ui.TextInput(label="Título", required=False, max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    cor = discord.ui.TextInput(label="Cor em hex (ex: FF0000)", required=False, max_length=7)
    imagem = discord.ui.TextInput(label="URL da imagem (opcional)", required=False)
    rodape = discord.ui.TextInput(label="Rodapé (opcional)", required=False, max_length=256)

    def __init__(self, mensagem: discord.Message):
        super().__init__()
        self.mensagem = mensagem
        atual = mensagem.embeds[0] if mensagem.embeds else None
        if atual:
            self.titulo.default = atual.title or ""
            self.descricao.default = atual.description or ""
            self.cor.default = f"{atual.color.value:06X}" if atual.color else ""
            self.imagem.default = atual.image.url if atual.image else ""
            self.rodape.default = atual.footer.text if atual.footer else ""

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.titulo.value or None,
            description=self.descricao.value or None,
            color=_cor_para_int(self.cor.value),
        )
        if self.imagem.value:
            embed.set_image(url=self.imagem.value)
        if self.rodape.value:
            embed.set_footer(text=self.rodape.value)

        await self.mensagem.edit(embed=embed)
        await interaction.response.send_message("✅ Embed editada.", ephemeral=True)


class Embeds(commands.Cog):
    """Comandos de embed customizada: abre um formulário (título, descrição,
    cor, imagem, rodapé) e publica no canal escolhido, sem precisar mexer em
    código ou JSON."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="criar-embed", description="Abre um formulário pra criar e enviar uma embed customizada.")
    @app_commands.describe(canal="Canal onde a embed vai ser enviada (padrão: este canal)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def criar_embed(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal_destino = canal or interaction.channel
        await interaction.response.send_modal(EmbedModal(canal_destino))

    @app_commands.command(name="editar-embed", description="Edita uma embed já enviada pelo bot.")
    @app_commands.describe(canal="Canal onde a mensagem está", id_mensagem="ID da mensagem com a embed")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def editar_embed(self, interaction: discord.Interaction, canal: discord.TextChannel, id_mensagem: str):
        try:
            mensagem = await canal.fetch_message(int(id_mensagem))
        except (discord.NotFound, ValueError):
            await interaction.response.send_message("Não encontrei essa mensagem nesse canal.", ephemeral=True)
            return

        if mensagem.author.id != interaction.client.user.id:
            await interaction.response.send_message("Só consigo editar embeds que eu mesmo enviei.", ephemeral=True)
            return

        await interaction.response.send_modal(EditarEmbedModal(mensagem))


async def setup(bot: commands.Bot):
    await bot.add_cog(Embeds(bot))
