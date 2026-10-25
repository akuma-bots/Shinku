import io
import logging

import discord
from discord import app_commands
from discord.ext import commands


class ListarIDsServidor(commands.Cog):
    """Gera um inventário dos canais, categorias e cargos do servidor NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="listar-ids-servidor",
        description="Gera um arquivo com os IDs de canais, categorias e cargos da NÊMESIS.",
    )
    @app_commands.guild_only()
    async def listar_ids_servidor(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado dentro do servidor NÊMESIS.",
                ephemeral=True,
            )
            return

        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "Por segurança, somente o proprietário da aplicação pode usar este comando.",
                ephemeral=True,
            )
            return

        guild_id = getattr(self.bot, "nemesis_guild_id", None)
        if guild_id is not None and interaction.guild.id != guild_id:
            await interaction.response.send_message(
                "Este comando só funciona no servidor NÊMESIS configurado para o bot.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            guild = interaction.guild
            lines = [
                f"INVENTÁRIO DISCORD — {guild.name}",
                f"Guild ID: {guild.id}",
                "",
                "=== CATEGORIAS E CANAIS ===",
            ]

            categories = sorted(
                (channel for channel in guild.channels if isinstance(channel, discord.CategoryChannel)),
                key=lambda item: item.position,
            )
            uncategorized = []
            for channel in guild.channels:
                if isinstance(channel, discord.CategoryChannel):
                    continue
                if channel.category_id is None:
                    uncategorized.append(channel)

            for category in categories:
                lines.append(f"\n[CATEGORIA] {category.name} | ID: {category.id}")
                children = sorted(category.channels, key=lambda item: (item.position, item.name.casefold()))
                for channel in children:
                    lines.append(
                        f"  [{channel.type}] #{channel.name} | ID: {channel.id}"
                    )

            if uncategorized:
                lines.append("\n[SEM CATEGORIA]")
                for channel in sorted(uncategorized, key=lambda item: (item.position, item.name.casefold())):
                    lines.append(f"  [{channel.type}] #{channel.name} | ID: {channel.id}")

            lines.extend(["", "=== CARGOS ==="])
            for role in sorted(guild.roles, key=lambda item: item.position, reverse=True):
                if role.is_default():
                    label = "@everyone"
                else:
                    label = role.name
                lines.append(f"{label} | ID: {role.id} | posição: {role.position}")

            payload = "\n".join(lines).encode("utf-8")
            file = discord.File(
                io.BytesIO(payload),
                filename=f"nemesis_ids_{guild.id}.txt",
            )
            await interaction.followup.send(
                content=(
                    "Inventário concluído. O arquivo contém os IDs atuais de todas as "
                    "categorias, canais e cargos deste servidor."
                ),
                file=file,
                ephemeral=True,
            )
            logging.info(
                "Inventário de IDs gerado pelo proprietário da aplicação para guild=%s (%s)",
                guild.name,
                guild.id,
            )
        except Exception:
            logging.exception("Falha ao gerar inventário de IDs do servidor.")
            await interaction.followup.send(
                "Não consegui gerar o inventário. A falha foi registrada nos logs do bot.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ListarIDsServidor(bot))
