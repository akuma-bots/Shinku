import discord
from discord import app_commands
from discord.ext import commands
from utils import loja
from utils.perfis import get_perfil, _salvar_perfil


class Loja(commands.Cog):
    """Loja de recompensas: troca XP por cargos cosméticos configurados
    pelos líderes. Gastar XP na loja não tira nenhuma patente que você já
    tenha conquistado — só reduz o XP disponível pra próxima promoção."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="loja-item-adicionar", description="Adiciona um item à loja de recompensas.")
    @app_commands.describe(nome="Nome do item", descricao="Descrição do item", preco_xp="Custo em XP",
                            cargo="Cargo dado ao comprar (opcional, pra itens cosméticos)")
    @app_commands.checks.has_permissions(administrator=True)
    async def loja_item_adicionar(self, interaction: discord.Interaction, nome: str, descricao: str,
                                   preco_xp: int, cargo: discord.Role = None):
        item = await loja.adicionar(interaction.guild.id, nome, descricao, preco_xp, cargo.id if cargo else None)
        await interaction.response.send_message(f"✅ Item **{nome}** adicionado (ID: `{item['id']}`, {preco_xp} XP).", ephemeral=True)

    @app_commands.command(name="loja-item-remover", description="Remove um item da loja.")
    @app_commands.describe(item_id="ID do item (aparece em /loja-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def loja_item_remover(self, interaction: discord.Interaction, item_id: str):
        ok = await loja.remover(interaction.guild.id, item_id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum item com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Item removido.", ephemeral=True)

    @app_commands.command(name="loja-listar", description="Lista os itens disponíveis na loja.")
    async def loja_listar(self, interaction: discord.Interaction):
        itens = await loja.listar(interaction.guild.id)
        if not itens:
            await interaction.response.send_message("A loja está vazia no momento.", ephemeral=True)
            return
        linhas = [f"**{i['nome']}** — {i['preco_xp']} XP (ID: `{i['id']}`)\n{i['descricao']}" for i in itens]
        embed = discord.Embed(title="🛒 Loja de recompensas", description="\n\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="loja-comprar", description="Compra um item da loja com seu XP.")
    @app_commands.describe(item_id="ID do item (aparece em /loja-listar)")
    async def loja_comprar(self, interaction: discord.Interaction, item_id: str):
        item = await loja.get(interaction.guild.id, item_id)
        if not item:
            await interaction.response.send_message("Não achei nenhum item com esse ID.", ephemeral=True)
            return

        perfil = await get_perfil(interaction.guild.id, interaction.user.id)
        if perfil["xp"] < item["preco_xp"]:
            await interaction.response.send_message(
                f"Você tem {perfil['xp']} XP, mas **{item['nome']}** custa {item['preco_xp']} XP.", ephemeral=True
            )
            return

        perfil["xp"] -= item["preco_xp"]
        await _salvar_perfil(interaction.guild.id, interaction.user.id, perfil)

        if item["cargo_id"]:
            cargo = interaction.guild.get_role(item["cargo_id"])
            if cargo:
                try:
                    await interaction.user.add_roles(cargo, reason=f"Comprou {item['nome']} na loja")
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(f"✅ Você comprou **{item['nome']}**! Restam {perfil['xp']} XP.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Loja(bot))