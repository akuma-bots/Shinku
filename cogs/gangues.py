import discord
from discord import app_commands
from discord.ext import commands
from utils import gangues


class Gangues(commands.Cog):
    """Cadastro de gangues: nome, líder, membros e emblema. Cada pessoa só
    pode estar em uma gangue por vez. O líder gerencia quem entra e sai, e
    pode transferir a liderança ou dissolver a gangue."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="gangue-criar", description="Cria uma nova gangue e te torna o líder.")
    @app_commands.describe(nome="Nome da gangue")
    async def gangue_criar(self, interaction: discord.Interaction, nome: str):
        if await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("Você já faz parte de uma gangue.", ephemeral=True)
            return
        if await gangues.get_por_nome(interaction.guild.id, nome):
            await interaction.response.send_message("Já existe uma gangue com esse nome.", ephemeral=True)
            return

        gangue = await gangues.criar(interaction.guild.id, nome, interaction.user.id)
        await interaction.response.send_message(f"✅ Gangue **{nome}** criada! Você é o líder (ID: `{gangue['id']}`).")

    @app_commands.command(name="gangue-adicionar-membro", description="Adiciona um membro à sua gangue (só o líder).")
    @app_commands.describe(membro="Quem adicionar")
    async def gangue_adicionar_membro(self, interaction: discord.Interaction, membro: discord.Member):
        gangue = await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id)
        if not gangue:
            await interaction.response.send_message("Você não lidera nenhuma gangue.", ephemeral=True)
            return
        if gangue["lider_id"] != interaction.user.id:
            await interaction.response.send_message("Só o líder da gangue pode fazer isso.", ephemeral=True)
            return
        if await gangues.get_gangue_do_membro(interaction.guild.id, membro.id):
            await interaction.response.send_message(f"{membro.mention} já está em uma gangue.", ephemeral=True)
            return

        await gangues.adicionar_membro(interaction.guild.id, gangue["id"], membro.id)
        await interaction.response.send_message(f"✅ {membro.mention} entrou na gangue **{gangue['nome']}**.")

    @app_commands.command(name="gangue-remover-membro", description="Remove um membro da sua gangue (só o líder).")
    @app_commands.describe(membro="Quem remover")
    async def gangue_remover_membro(self, interaction: discord.Interaction, membro: discord.Member):
        gangue = await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id)
        if not gangue:
            await interaction.response.send_message("Você não lidera nenhuma gangue.", ephemeral=True)
            return
        if gangue["lider_id"] != interaction.user.id:
            await interaction.response.send_message("Só o líder da gangue pode fazer isso.", ephemeral=True)
            return
        if membro.id == gangue["lider_id"]:
            await interaction.response.send_message("O líder não pode se remover — use `/gangue-transferir-lideranca` ou `/gangue-dissolver`.", ephemeral=True)
            return

        ok = await gangues.remover_membro(interaction.guild.id, gangue["id"], membro.id)
        if not ok:
            await interaction.response.send_message(f"{membro.mention} não está nessa gangue.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {membro.mention} saiu da gangue **{gangue['nome']}**.")

    @app_commands.command(name="gangue-emblema", description="Define o emblema (imagem) da sua gangue.")
    @app_commands.describe(imagem="Imagem do emblema")
    async def gangue_emblema(self, interaction: discord.Interaction, imagem: discord.Attachment):
        gangue = await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id)
        if not gangue:
            await interaction.response.send_message("Você não lidera nenhuma gangue.", ephemeral=True)
            return
        if gangue["lider_id"] != interaction.user.id:
            await interaction.response.send_message("Só o líder da gangue pode fazer isso.", ephemeral=True)
            return
        await gangues.definir_emblema(interaction.guild.id, gangue["id"], imagem.url)
        await interaction.response.send_message("✅ Emblema atualizado.", ephemeral=True)

    @app_commands.command(name="gangue-transferir-lideranca", description="Transfere a liderança da sua gangue pra outro membro dela.")
    @app_commands.describe(novo_lider="Novo líder (precisa já estar na gangue)")
    async def gangue_transferir_lideranca(self, interaction: discord.Interaction, novo_lider: discord.Member):
        gangue = await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id)
        if not gangue:
            await interaction.response.send_message("Você não lidera nenhuma gangue.", ephemeral=True)
            return
        if gangue["lider_id"] != interaction.user.id:
            await interaction.response.send_message("Só o líder da gangue pode fazer isso.", ephemeral=True)
            return
        ok = await gangues.transferir_lideranca(interaction.guild.id, gangue["id"], novo_lider.id)
        if not ok:
            await interaction.response.send_message(f"{novo_lider.mention} precisa já estar na gangue.", ephemeral=True)
            return
        await interaction.response.send_message(f"👑 {novo_lider.mention} agora lidera a gangue **{gangue['nome']}**.")

    @app_commands.command(name="gangue-dissolver", description="Dissolve sua gangue (só o líder).")
    async def gangue_dissolver(self, interaction: discord.Interaction):
        gangue = await gangues.get_gangue_do_membro(interaction.guild.id, interaction.user.id)
        if not gangue:
            await interaction.response.send_message("Você não lidera nenhuma gangue.", ephemeral=True)
            return
        if gangue["lider_id"] != interaction.user.id:
            await interaction.response.send_message("Só o líder da gangue pode fazer isso.", ephemeral=True)
            return
        await gangues.dissolver(interaction.guild.id, gangue["id"])
        await interaction.response.send_message(f"💥 Gangue **{gangue['nome']}** dissolvida.")

    @app_commands.command(name="gangue-info", description="Mostra os detalhes de uma gangue.")
    @app_commands.describe(nome="Nome da gangue")
    async def gangue_info(self, interaction: discord.Interaction, nome: str):
        gangue = await gangues.get_por_nome(interaction.guild.id, nome)
        if not gangue:
            await interaction.response.send_message("Não achei nenhuma gangue com esse nome.", ephemeral=True)
            return
        membros_texto = "\n".join(f"{'👑 ' if uid == gangue['lider_id'] else '• '}<@{uid}>" for uid in gangue["membros"])
        embed = discord.Embed(title=f"🏴 {gangue['nome']}", description=membros_texto, color=0x5865F2)
        if gangue["emblema_url"]:
            embed.set_thumbnail(url=gangue["emblema_url"])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gangue-listar", description="Lista todas as gangues do servidor.")
    async def gangue_listar(self, interaction: discord.Interaction):
        lista = await gangues.listar(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhuma gangue criada ainda.", ephemeral=True)
            return
        linhas = [f"**{g['nome']}** — líder: <@{g['lider_id']}> ({len(g['membros'])} membro(s))" for g in lista]
        embed = discord.Embed(title="🏴 Gangues do servidor", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gangues(bot))