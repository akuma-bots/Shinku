from utils.apresentacao import criar_embed
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands
from utils import loja
from utils.perfis import get_perfil, _salvar_perfil

_LOG = logging.getLogger(__name__)
_COMPRA_LOCK = asyncio.Lock()


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
        try:
            item = await loja.adicionar(
                interaction.guild.id, nome, descricao, preco_xp,
                cargo.id if cargo else None,
            )
        except ValueError as erro:
            await interaction.response.send_message(f"❌ {erro}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Item **{item['nome']}** adicionado (ID: `{item['id']}`, {item['preco_xp']} XP).",
            ephemeral=True,
        )

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
        embed = criar_embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  ARSENAL DE RECOMPENSAS", description="\n\n".join(linhas), color=0xB51F32)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="loja-comprar", description="Compra um item da loja com seu XP.")
    @app_commands.describe(item_id="ID do item (aparece em /loja-listar)")
    async def loja_comprar(self, interaction: discord.Interaction, item_id: str):
        # Serializa compras no processo para evitar duas interações debitarem
        # o mesmo saldo lido antes da primeira gravação.
        async with _COMPRA_LOCK:
            item = await loja.get(interaction.guild.id, item_id)
            if not item:
                await interaction.response.send_message("Não achei nenhum item com esse ID.", ephemeral=True)
                return

            membro = interaction.user
            cargo = None
            if item.get("cargo_id"):
                cargo = interaction.guild.get_role(item["cargo_id"])
                if cargo is None:
                    await interaction.response.send_message(
                        "Este item está temporariamente indisponível: o cargo configurado não existe mais. Avise a administração.",
                        ephemeral=True,
                    )
                    return
                if cargo in membro.roles:
                    await interaction.response.send_message(
                        f"Você já possui o cargo **{cargo.name}**; não foi descontado XP.",
                        ephemeral=True,
                    )
                    return
                bot_member = interaction.guild.me
                if bot_member is None or not bot_member.guild_permissions.manage_roles or cargo >= bot_member.top_role:
                    await interaction.response.send_message(
                        "Não consigo entregar o cargo deste item. A administração precisa conferir minhas permissões e a hierarquia de cargos. Nenhum XP foi descontado.",
                        ephemeral=True,
                    )
                    return

            perfil = await get_perfil(interaction.guild.id, membro.id)
            try:
                xp_atual = max(0, int(perfil.get("xp", 0) or 0))
                preco = int(item["preco_xp"])
            except (TypeError, ValueError, OverflowError):
                await interaction.response.send_message(
                    "Não consegui validar seu saldo ou o preço deste item. Nenhum XP foi descontado.",
                    ephemeral=True,
                )
                return
            if preco < 0:
                await interaction.response.send_message(
                    "Este item tem um preço inválido e foi bloqueado. Avise a administração.",
                    ephemeral=True,
                )
                return
            if xp_atual < preco:
                await interaction.response.send_message(
                    f"Você tem {xp_atual} XP, mas **{item['nome']}** custa {preco} XP.",
                    ephemeral=True,
                )
                return

            perfil["xp"] = xp_atual - preco
            await _salvar_perfil(interaction.guild.id, membro.id, perfil)

            if cargo is not None:
                try:
                    await membro.add_roles(cargo, reason=f"Comprou {item['nome']} na loja")
                except (discord.Forbidden, discord.HTTPException) as erro:
                    # A compra não pode cobrar por um benefício que o bot não
                    # conseguiu entregar; tenta estornar o saldo debitado.
                    try:
                        perfil["xp"] = xp_atual
                        await _salvar_perfil(interaction.guild.id, membro.id, perfil)
                    except Exception:
                        _LOG.exception(
                            "Falha ao estornar XP da compra %s para usuário %s.",
                            item["id"], membro.id,
                        )
                        await interaction.response.send_message(
                            "Não consegui entregar o cargo nem confirmar o estorno automático. Avise a administração antes de tentar comprar novamente.",
                            ephemeral=True,
                        )
                        return
                    _LOG.warning(
                        "Compra %s falhou ao atribuir cargo %s: %s",
                        item["id"], cargo.id, erro,
                    )
                    await interaction.response.send_message(
                        "Não consegui entregar o cargo e o XP foi estornado. Tente novamente mais tarde.",
                        ephemeral=True,
                    )
                    return

            await interaction.response.send_message(
                f"✅ Você comprou **{item['nome']}**! Restam {perfil['xp']} XP."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Loja(bot))