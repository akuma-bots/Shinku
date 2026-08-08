import time
import uuid
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar, salvar

ARQUIVO = "sorteios.json"  # { sorteio_id: {guild_id, canal_id, mensagem_id, premio, fim, vencedores, participantes, encerrado} }


class BotaoParticipar(discord.ui.View):
    """View persistente — um único botão, o sorteio de verdade é identificado
    pelo ID da mensagem em que o botão está, não por instância da view."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.primary, custom_id="sorteio_participar_btn")
    async def participar(self, interaction: discord.Interaction, button: discord.ui.Button):
        todos = await carregar(ARQUIVO, {})
        sorteio = next((s for s in todos.values() if s["mensagem_id"] == interaction.message.id), None)
        if not sorteio or sorteio["encerrado"]:
            await interaction.response.send_message("Esse sorteio já acabou.", ephemeral=True)
            return

        if interaction.user.id in sorteio["participantes"]:
            await interaction.response.send_message("Você já está participando! 🎉", ephemeral=True)
            return

        sorteio["participantes"].append(interaction.user.id)
        todos[sorteio["id"]] = sorteio
        await salvar(ARQUIVO, todos)
        await interaction.response.send_message("✅ Você entrou no sorteio! Boa sorte 🍀", ephemeral=True)


class Sorteios(commands.Cog):
    """Sorteios com botão de participar — sorteia vencedores sozinho quando o prazo acaba."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(BotaoParticipar())
        self.verificar_sorteios.start()

    def cog_unload(self):
        self.verificar_sorteios.cancel()

    @app_commands.command(name="sorteio-criar", description="Cria um sorteio com botão de participar.")
    @app_commands.describe(premio="O que vai ser sorteado", duracao_minutos="Duração em minutos", vencedores="Quantos vencedores (padrão 1)", canal="Canal onde postar (padrão: este canal)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sorteio_criar(self, interaction: discord.Interaction, premio: str, duracao_minutos: int, vencedores: int = 1, canal: discord.TextChannel = None):
        canal_destino = canal or interaction.channel
        fim = time.time() + duracao_minutos * 60

        embed = discord.Embed(
            title="🎉 SORTEIO!",
            description=f"**Prêmio:** {premio}\n**Vencedores:** {vencedores}\n**Termina:** <t:{int(fim)}:R>\n\nClique no botão abaixo pra participar!",
            color=0xFEE75C,
        )
        embed.set_footer(text=f"Sorteio criado por {interaction.user}")

        await interaction.response.send_message("Criando sorteio...", ephemeral=True)
        mensagem = await canal_destino.send(embed=embed, view=BotaoParticipar())

        sorteio_id = str(uuid.uuid4())[:8]
        todos = await carregar(ARQUIVO, {})
        todos[sorteio_id] = {
            "id": sorteio_id,
            "guild_id": interaction.guild.id,
            "canal_id": canal_destino.id,
            "mensagem_id": mensagem.id,
            "premio": premio,
            "fim": fim,
            "vencedores": vencedores,
            "participantes": [],
            "encerrado": False,
        }
        await salvar(ARQUIVO, todos)

        await interaction.edit_original_response(content=f"✅ Sorteio criado em {canal_destino.mention}.")

    @app_commands.command(name="sorteio-encerrar", description="Encerra um sorteio na hora e já sorteia os vencedores.")
    @app_commands.describe(id="ID do sorteio (aparece no /sorteio-listar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sorteio_encerrar(self, interaction: discord.Interaction, id: str):
        todos = await carregar(ARQUIVO, {})
        sorteio = todos.get(id)
        if not sorteio or sorteio["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("Não achei esse sorteio.", ephemeral=True)
            return
        await interaction.response.send_message("Encerrando...", ephemeral=True)
        await self._sortear_vencedores(sorteio)

    @app_commands.command(name="sorteio-listar", description="Lista os sorteios em andamento neste servidor.")
    async def sorteio_listar(self, interaction: discord.Interaction):
        todos = await carregar(ARQUIVO, {})
        ativos = [s for s in todos.values() if s["guild_id"] == interaction.guild.id and not s["encerrado"]]
        if not ativos:
            await interaction.response.send_message("Nenhum sorteio em andamento.", ephemeral=True)
            return
        linhas = [f"**#{s['id']}** — {s['premio']} ({len(s['participantes'])} participantes, termina <t:{int(s['fim'])}:R>)" for s in ativos]
        await interaction.response.send_message("\n".join(linhas), ephemeral=True)

    async def _sortear_vencedores(self, sorteio: dict):
        todos = await carregar(ARQUIVO, {})
        sorteio["encerrado"] = True
        todos[sorteio["id"]] = sorteio
        await salvar(ARQUIVO, todos)

        canal = self.bot.get_channel(sorteio["canal_id"])
        if not canal:
            return

        participantes = sorteio["participantes"]
        if not participantes:
            await canal.send(f"🎉 O sorteio de **{sorteio['premio']}** acabou, mas ninguém participou.")
            return

        qtd = min(sorteio["vencedores"], len(participantes))
        vencedores_ids = random.sample(participantes, qtd)
        mencoes = ", ".join(f"<@{uid}>" for uid in vencedores_ids)
        await canal.send(f"🎉 Sorteio de **{sorteio['premio']}** encerrado! Vencedor(es): {mencoes}")

    @tasks.loop(seconds=60)
    async def verificar_sorteios(self):
        todos = await carregar(ARQUIVO, {})
        agora = time.time()
        for sorteio in list(todos.values()):
            if not sorteio["encerrado"] and agora >= sorteio["fim"]:
                await self._sortear_vencedores(sorteio)

    @verificar_sorteios.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Sorteios(bot))
