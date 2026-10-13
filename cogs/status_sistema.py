import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import USANDO_UPSTASH, verificar_conexao_compartilhada


class StatusSistema(commands.GroupCog, group_name="sistema", group_description="Diagnóstico dos sistemas da NÊMESIS"):
    """Comandos administrativos para verificar a saúde do Shinku."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="status", description="Mostra o estado atual do bot e dos sistemas carregados.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor da NÊMESIS.", ephemeral=True)
            return

        falhas = getattr(self.bot, "cogs_falhos", [])
        comando_count = len(self.bot.tree.get_commands(guild=guild))
        embed = discord.Embed(
            title="NÊMESIS • Status do sistema",
            color=0x57F287 if self.bot.is_ready() and not falhas else 0xED4245,
        )
        embed.add_field(name="Discord", value="Online" if self.bot.is_ready() else "Inicializando", inline=True)
        embed.add_field(name="Servidor", value="Conectado" if self.bot.get_guild(guild.id) else "Não encontrado", inline=True)
        embed.add_field(name="Armazenamento", value="Upstash" if USANDO_UPSTASH else "Local", inline=True)
        embed.add_field(name="Cogs carregados", value=str(len(self.bot.cogs)), inline=True)
        embed.add_field(name="Comandos locais", value=str(comando_count), inline=True)
        embed.add_field(name="Cogs com falha", value=str(len(falhas)), inline=True)
        if falhas:
            embed.add_field(
                name="Falhas de inicialização",
                value="\n".join(f"• {item.get('cog', 'desconhecido')}" for item in falhas[:10])[:1024],
                inline=False,
            )
        embed.set_footer(text="NÊMESIS • Diagnóstico administrativo")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="diagnostico", description="Testa a conexão com o armazenamento compartilhado.")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not USANDO_UPSTASH:
            await interaction.followup.send(
                "⚠️ O bot está usando armazenamento local. A sincronização compartilhada com o site não está ativa.",
                ephemeral=True,
            )
            return

        try:
            await asyncio.wait_for(verificar_conexao_compartilhada(), timeout=8)
        except asyncio.TimeoutError:
            logging.warning("Diagnóstico manual: timeout ao verificar o armazenamento compartilhado.")
            await interaction.followup.send("❌ O armazenamento compartilhado demorou mais de 8 segundos para responder.", ephemeral=True)
            return
        except Exception as erro:
            logging.exception("Diagnóstico manual: falha no armazenamento compartilhado.")
            await interaction.followup.send(
                f"❌ Falha no armazenamento compartilhado: `{type(erro).__name__}`. Confira os logs do Render.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "✅ O armazenamento compartilhado respondeu. Isso confirma a conectividade do Redis, mas não substitui a verificação de cada fluxo do site.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusSistema(bot))
