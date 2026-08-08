import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.guild_config import get_config, set_config
from utils.memoria import ensinar_fato, listar_fatos, esquecer_fato
from utils.atualizacao import get_atualizacao_de_hoje, atualizar_agora


class Aprendizado(commands.Cog):
    """IA adaptativa, mas supervisionada: a equipe ensina fatos de propósito
    (/ensinar), o bot lembra sozinho das conversas recentes (automático, veja
    utils/memoria.py), e uma vez por dia o bot pesquisa na web sozinho sobre
    um tema (padrão: novidades do Gakuran) pra se manter atualizado.

    Por que não é 100% automático: deixar o bot 'aprender' qualquer coisa
    que qualquer pessoa disser no chat, sem revisão, é perigoso — alguém mal
    intencionado poderia ensinar informação falsa ou ofensiva de propósito,
    e o bot repetiria depois pra todo mundo. Por isso só quem tem permissão
    de Gerenciar Servidor pode ensinar fatos permanentes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.atualizacao_diaria_automatica.start()

    def cog_unload(self):
        self.atualizacao_diaria_automatica.cancel()

    @app_commands.command(name="ensinar", description="Ensina um fato permanente pro bot lembrar nas conversas (só equipe).")
    @app_commands.describe(fato="O que o bot deve saber a partir de agora")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ensinar(self, interaction: discord.Interaction, fato: str):
        await ensinar_fato(interaction.guild.id, fato, interaction.user.id)
        await interaction.response.send_message(f"🧠 Aprendido: \"{fato}\"\nJá vale pra próxima conversa.", ephemeral=True)

    @app_commands.command(name="fatos-ensinados", description="Lista o que a equipe já ensinou pro bot neste servidor.")
    async def fatos_ensinados(self, interaction: discord.Interaction):
        fatos = await listar_fatos(interaction.guild.id)
        if not fatos:
            await interaction.response.send_message("Nada ensinado ainda. Use `/ensinar` pra adicionar.", ephemeral=True)
            return
        linhas = [f"**{i}.** {f['fato']} (por <@{f['ensinado_por_id']}>)" for i, f in enumerate(fatos)]
        embed = discord.Embed(title="🧠 Fatos ensinados", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="esquecer-fato", description="Remove um fato ensinado (veja o número em /fatos-ensinados).")
    @app_commands.describe(numero="O número do fato, mostrado em /fatos-ensinados")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def esquecer_fato_cmd(self, interaction: discord.Interaction, numero: int):
        ok = await esquecer_fato(interaction.guild.id, numero)
        if ok:
            await interaction.response.send_message(f"🗑️ Fato #{numero} esquecido.", ephemeral=True)
        else:
            await interaction.response.send_message("Não achei um fato com esse número.", ephemeral=True)

    @app_commands.command(name="configurar-tema-diario", description="Define sobre o que o bot pesquisa sozinho todo dia (padrão: novidades do Gakuran).")
    @app_commands.describe(tema="Ex: 'notícias de tecnologia', 'atualizações do jogo X'")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_tema_diario(self, interaction: discord.Interaction, tema: str):
        await set_config(interaction.guild.id, tema_diario=tema)
        await interaction.response.send_message(f"✅ A partir de amanhã o bot pesquisa sozinho sobre: **{tema}**", ephemeral=True)

    @app_commands.command(name="atualizar-agora", description="Força a pesquisa diária agora, sem esperar o ciclo automático.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def atualizar_agora_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await get_config(interaction.guild.id)
        registro = await atualizar_agora(interaction.guild.id, config.get("tema_diario"))
        await interaction.followup.send(f"🔄 Atualizado! Tema: **{registro['tema']}**\n\n{registro['resumo'][:1500]}", ephemeral=True)

    @tasks.loop(hours=6)
    async def atualizacao_diaria_automatica(self):
        for guild in self.bot.guilds:
            existente = await get_atualizacao_de_hoje(guild.id)
            if existente:
                continue  # já atualizou hoje, não gasta pesquisa à toa
            config = await get_config(guild.id)
            await atualizar_agora(guild.id, config.get("tema_diario"))

    @atualizacao_diaria_automatica.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Aprendizado(bot))
