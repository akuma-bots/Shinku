import discord
from discord import app_commands
from discord.ext import commands
from utils.guild_config import get_config, set_config


class Configuracao(commands.Cog):
    """Permite que cada servidor configure o bot para o próprio uso."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="configurar", description="Configura o bot para este servidor (cargo de suporte, canal de logs, categoria de tickets).")
    @app_commands.describe(
        cargo_suporte="Cargo chamado quando um ticket precisa de atendimento humano",
        canal_logs="Canal onde o bot registra avisos, bans, kicks e mutes",
        categoria_tickets="Categoria onde os canais de ticket serão criados",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar(
        self,
        interaction: discord.Interaction,
        cargo_suporte: discord.Role = None,
        canal_logs: discord.TextChannel = None,
        categoria_tickets: discord.CategoryChannel = None,
    ):
        if not any([cargo_suporte, canal_logs, categoria_tickets]):
            config_atual = await get_config(interaction.guild.id)
            embed = discord.Embed(title="⚙️ Configuração atual deste servidor", color=0x5865F2)
            embed.add_field(
                name="Cargo de suporte",
                value=f"<@&{config_atual['support_role_id']}>" if config_atual["support_role_id"] else "não definido",
                inline=False,
            )
            embed.add_field(
                name="Canal de logs",
                value=f"<#{config_atual['log_channel_id']}>" if config_atual["log_channel_id"] else "não definido",
                inline=False,
            )
            embed.add_field(
                name="Categoria de tickets",
                value=f"<#{config_atual['ticket_category_id']}>" if config_atual["ticket_category_id"] else "não definido (cria na raiz do servidor)",
                inline=False,
            )
            embed.set_footer(text="Use /configurar com os parâmetros para alterar.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        novo = await set_config(
            interaction.guild.id,
            support_role_id=cargo_suporte.id if cargo_suporte else None,
            log_channel_id=canal_logs.id if canal_logs else None,
            ticket_category_id=categoria_tickets.id if categoria_tickets else None,
        )

        partes = []
        if cargo_suporte:
            partes.append(f"Cargo de suporte definido como {cargo_suporte.mention}")
        if canal_logs:
            partes.append(f"Canal de logs definido como {canal_logs.mention}")
        if categoria_tickets:
            partes.append(f"Categoria de tickets definida como {categoria_tickets.mention}")

        await interaction.response.send_message("✅ " + "\n✅ ".join(partes), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar Servidor** para configurar o bot.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Configuracao(bot))
