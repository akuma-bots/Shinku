import discord
from discord import app_commands
from discord.ext import commands


def _cor_para_int(valor: str) -> int:
    valor = (valor or "").strip().lstrip("#")
    try:
        return int(valor, 16) if valor else 0x5865F2
    except ValueError:
        return 0x5865F2


def _view_com_botoes(botao1_texto, botao1_url, botao2_texto, botao2_url):
    """Monta uma View só com botões de LINK (não precisam de código de resposta,
    então funcionam pra sempre, mesmo depois do bot reiniciar)."""
    view = discord.ui.View(timeout=None)
    tem_botao = False
    if botao1_texto and botao1_url:
        view.add_item(discord.ui.Button(label=botao1_texto[:80], url=botao1_url, style=discord.ButtonStyle.link))
        tem_botao = True
    if botao2_texto and botao2_url:
        view.add_item(discord.ui.Button(label=botao2_texto[:80], url=botao2_url, style=discord.ButtonStyle.link))
        tem_botao = True
    return view if tem_botao else None


class EmbedModal(discord.ui.Modal, title="Criar embed"):
    titulo = discord.ui.TextInput(label="Título", required=False, max_length=256)
    descricao = discord.ui.TextInput(
        label="Descrição (aceita **negrito**, • listas)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )
    cor = discord.ui.TextInput(label="Cor em hex (ex: FFD700 pra dourado)", required=False, max_length=7, placeholder="5865F2")
    imagem = discord.ui.TextInput(label="URL da imagem/banner (opcional)", required=False)
    rodape = discord.ui.TextInput(label="Rodapé (opcional)", required=False, max_length=256)

    def __init__(self, canal: discord.TextChannel, botao1_texto=None, botao1_url=None, botao2_texto=None, botao2_url=None):
        super().__init__()
        self.canal = canal
        self.botao1_texto = botao1_texto
        self.botao1_url = botao1_url
        self.botao2_texto = botao2_texto
        self.botao2_url = botao2_url

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

        view = _view_com_botoes(self.botao1_texto, self.botao1_url, self.botao2_texto, self.botao2_url)
        await self.canal.send(embed=embed, view=view)
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
    cor, imagem, rodapé) e publica no canal escolhido, com opção de até 2
    botões de link embaixo — pra deixar painéis com visual profissional."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="criar-embed", description="Abre um formulário pra criar e enviar uma embed customizada, com botões opcionais.")
    @app_commands.describe(
        canal="Canal onde a embed vai ser enviada (padrão: este canal)",
        botao1_texto="Texto do 1º botão (opcional, ex: '🌐 Nosso site')",
        botao1_url="Link do 1º botão (obrigatório se usar o texto acima)",
        botao2_texto="Texto do 2º botão (opcional)",
        botao2_url="Link do 2º botão (obrigatório se usar o texto acima)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def criar_embed(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        botao1_texto: str = None,
        botao1_url: str = None,
        botao2_texto: str = None,
        botao2_url: str = None,
    ):
        canal_destino = canal or interaction.channel
        await interaction.response.send_modal(
            EmbedModal(canal_destino, botao1_texto, botao1_url, botao2_texto, botao2_url)
        )

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
