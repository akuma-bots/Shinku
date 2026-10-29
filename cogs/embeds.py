from utils.apresentacao import criar_embed
import discord
from discord import app_commands
from discord.ext import commands


def _cor_para_int(valor: str) -> int:
    valor = (valor or "").strip().lstrip("#")
    try:
        return int(valor, 16) if valor else 0xB51F32
    except ValueError:
        return 0xB51F32


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


class EmbedModal(discord.ui.Modal, title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ CRIAR MODELO"):
    parte1 = discord.ui.TextInput(label="Descrição — parte 1/5", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    parte2 = discord.ui.TextInput(label="Descrição — parte 2/5", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    parte3 = discord.ui.TextInput(label="Descrição — parte 3/5", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    parte4 = discord.ui.TextInput(label="Descrição — parte 4/5", style=discord.TextStyle.paragraph, required=False, max_length=4000)
    parte5 = discord.ui.TextInput(label="Descrição — parte 5/5", style=discord.TextStyle.paragraph, required=False, max_length=4000)

    def __init__(
        self,
        canal: discord.TextChannel,
        titulo="",
        cor="B51F32",
        imagem="",
        rodape="",
        botao1_texto=None,
        botao1_url=None,
        botao2_texto=None,
        botao2_url=None,
    ):
        super().__init__()
        self.canal = canal
        self.titulo_embed = (titulo or "").strip()[:256]
        self.cor_embed = _cor_para_int(cor)
        self.imagem_embed = (imagem or "").strip()
        self.rodape_embed = (rodape or "").strip()[:2048]
        self.botao1_texto = (botao1_texto or "").strip()
        self.botao1_url = (botao1_url or "").strip()
        self.botao2_texto = (botao2_texto or "").strip()
        self.botao2_url = (botao2_url or "").strip()

    async def on_submit(self, interaction: discord.Interaction):
        partes = [
            campo.value
            for campo in (self.parte1, self.parte2, self.parte3, self.parte4, self.parte5)
            if campo.value
        ]
        if not partes:
            partes = [""]

        total = sum(len(parte) for parte in partes)
        if total > 20000:
            await interaction.response.send_message(
                "A descrição pode ter no máximo 20.000 caracteres.",
                ephemeral=True,
            )
            return

        for nome, url in (
            ("Botão 1", self.botao1_url),
            ("Botão 2", self.botao2_url),
            ("Imagem", self.imagem_embed),
        ):
            if url and not url.startswith(("https://", "http://")):
                await interaction.response.send_message(
                    "{}: informe uma URL iniciada por http:// ou https://.".format(nome),
                    ephemeral=True,
                )
                return

        view = _view_com_botoes(
            self.botao1_texto,
            self.botao1_url,
            self.botao2_texto,
            self.botao2_url,
        )
        await interaction.response.defer(ephemeral=True, thinking=True)

        enviados = 0
        try:
            for indice, texto in enumerate(partes):
                titulo = self.titulo_embed
                if indice > 0:
                    sufixo = " — continuação {}/{}".format(indice + 1, len(partes))
                    titulo = "{}{}".format(titulo[:256 - len(sufixo)], sufixo) if titulo else "Continuação {}/{}".format(indice + 1, len(partes))

                embed = criar_embed(
                    title=titulo or None,
                    description=texto or None,
                    color=self.cor_embed,
                )
                if indice == 0:
                    if self.imagem_embed:
                        embed.set_image(url=self.imagem_embed)
                    if self.rodape_embed:
                        embed.set_footer(text=self.rodape_embed)

                await self.canal.send(embed=embed, view=view if indice == 0 else None)
                enviados += 1
        except discord.HTTPException as erro:
            await interaction.followup.send(
                "Não consegui enviar todas as partes. Foram enviadas {} de {} mensagens. Erro: {}".format(enviados, len(partes), erro),
                ephemeral=True,
            )
            return

        mensagem = "✅ Embed publicada em {}. Foram enviadas {} mensagem(ns), com {:,} caracteres no total.".format(self.canal.mention, enviados, total).replace(",", ".")
        await interaction.followup.send(mensagem, ephemeral=True)


class EditarEmbedModal(discord.ui.Modal, title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ EDITAR MODELO"):
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
        embed = criar_embed(
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

    @app_commands.command(
        name="criar-embed",
        description="Cria uma embed com descrição de até 20.000 caracteres.",
    )
    @app_commands.describe(
        canal="Canal onde as mensagens serão enviadas (padrão: este canal)",
        titulo="Título da embed (opcional)",
        cor="Cor em hexadecimal, por exemplo B51F32",
        imagem="URL da imagem/banner (opcional)",
        rodape="Texto do rodapé (opcional)",
        botao1_texto="Texto do primeiro botão de link (opcional)",
        botao1_url="URL do primeiro botão (obrigatória se usar o texto)",
        botao2_texto="Texto do segundo botão de link (opcional)",
        botao2_url="URL do segundo botão (obrigatória se usar o texto)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def criar_embed(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        titulo: str = None,
        cor: str = "B51F32",
        imagem: str = None,
        rodape: str = None,
        botao1_texto: str = None,
        botao1_url: str = None,
        botao2_texto: str = None,
        botao2_url: str = None,
    ):
        if bool(botao1_texto) != bool(botao1_url) or bool(botao2_texto) != bool(botao2_url):
            await interaction.response.send_message(
                "Para cada botão, preencha o texto e a URL.",
                ephemeral=True,
            )
            return

        canal_destino = canal or interaction.channel
        if not isinstance(canal_destino, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Escolha um canal de texto válido.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            EmbedModal(
                canal_destino,
                titulo=titulo,
                cor=cor,
                imagem=imagem,
                rodape=rodape,
                botao1_texto=botao1_texto,
                botao1_url=botao1_url,
                botao2_texto=botao2_texto,
                botao2_url=botao2_url,
            )
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
