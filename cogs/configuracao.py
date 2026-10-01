import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import (
    get_config,
    set_config,
)


class Configuracao(commands.Cog):
    """
    Configuração interna do servidor oficial da NÊMESIS.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot


    @app_commands.command(
        name="configurar",
        description=(
            "Configura os principais recursos "
            "da NÊMESIS."
        ),
    )
    @app_commands.describe(
        cargo_suporte=(
            "Cargo responsável pelo atendimento."
        ),
        canal_logs=(
            "Canal utilizado para os registros."
        ),
        categoria_tickets=(
            "Categoria onde os tickets serão criados."
        ),
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        cargo_suporte: discord.Role = None,
        canal_logs: discord.TextChannel = None,
        categoria_tickets: discord.CategoryChannel = None,
    ):

        if not any(
            [
                cargo_suporte,
                canal_logs,
                categoria_tickets,
            ]
        ):

            config_atual = await get_config(
                interaction.guild.id
            )

            embed = discord.Embed(
                title="⚙️ Configuração — NÊMESIS",
                description=(
                    "Configurações atualmente "
                    "registradas para a NÊMESIS."
                ),
                color=0x5865F2,
            )

            embed.add_field(
                name="Cargo de suporte",
                value=(
                    f"<@&{config_atual['support_role_id']}>"
                    if config_atual["support_role_id"]
                    else "Não definido"
                ),
                inline=False,
            )

            embed.add_field(
                name="Canal de logs",
                value=(
                    f"<#{config_atual['log_channel_id']}>"
                    if config_atual["log_channel_id"]
                    else "Não definido"
                ),
                inline=False,
            )

            embed.add_field(
                name="Categoria de tickets",
                value=(
                    f"<#{config_atual['ticket_category_id']}>"
                    if config_atual["ticket_category_id"]
                    else "Não definida"
                ),
                inline=False,
            )

            embed.set_footer(
                text=(
                    "NÊMESIS • Configuração interna"
                )
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

            return


        await set_config(
            interaction.guild.id,

            support_role_id=(
                cargo_suporte.id
                if cargo_suporte
                else None
            ),

            log_channel_id=(
                canal_logs.id
                if canal_logs
                else None
            ),

            ticket_category_id=(
                categoria_tickets.id
                if categoria_tickets
                else None
            ),
        )


        partes = []


        if cargo_suporte:

            partes.append(
                "Cargo de suporte definido como "
                f"{cargo_suporte.mention}"
            )


        if canal_logs:

            partes.append(
                "Canal de logs definido como "
                f"{canal_logs.mention}"
            )


        if categoria_tickets:

            partes.append(
                "Categoria de tickets definida como "
                f"{categoria_tickets.mention}"
            )


        await interaction.response.send_message(
            "⚙️ **NÊMESIS configurada.**\n\n"
            + "\n".join(
                f"• {parte}"
                for parte in partes
            ),
            ephemeral=True,
        )


    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):

        if isinstance(
            error,
            app_commands.MissingPermissions,
        ):

            mensagem = (
                "Você precisa da permissão "
                "**Gerenciar Servidor** para "
                "alterar as configurações da NÊMESIS."
            )

            if interaction.response.is_done():

                await interaction.followup.send(
                    mensagem,
                    ephemeral=True,
                )

            else:

                await interaction.response.send_message(
                    mensagem,
                    ephemeral=True,
                )

            return


        raise error


async def setup(
    bot: commands.Bot,
):
    await bot.add_cog(
        Configuracao(bot)
    )