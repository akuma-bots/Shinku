import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import COR_ERRO, COR_SUCESSO, COR_AVISO, criar_embed
from utils.storage import USANDO_UPSTASH, verificar_conexao_storage


class StatusSistema(commands.GroupCog, group_name="sistema", group_description="Diagnóstico dos sistemas da NÊMESIS"):
    """Painel administrativo de estado e diagnóstico da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._inicio = time.monotonic()

    @app_commands.command(name="status", description="Mostra a saúde, latência e os módulos ativos do bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor da NÊMESIS.", ephemeral=True)
            return

        falhas = getattr(self.bot, "cogs_falhos", [])
        latencia_ms = round(self.bot.latency * 1000) if self.bot.latency is not None else None
        comandos = self.bot.tree.get_commands(guild=guild)
        uptime = max(0, int(time.monotonic() - self._inicio))
        horas, resto = divmod(uptime, 3600)
        minutos, segundos = divmod(resto, 60)
        estado_ok = self.bot.is_ready() and not falhas
        embed = criar_embed(
            "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE SISTEMA ・✦",
            "Visão operacional do bot e dos módulos carregados.",
            cor=COR_SUCESSO if estado_ok else COR_AVISO if self.bot.is_ready() else COR_ERRO,
            rodape="NÊMESIS • Diagnóstico administrativo",
            timestamp=True,
        )
        embed.add_field(name="◈ CONEXÃO DISCORD", value="🟢 Online" if self.bot.is_ready() else "🔴 Inicializando", inline=True)
        embed.add_field(name="◈ LATÊNCIA", value=f"{latencia_ms} ms" if latencia_ms is not None else "Indisponível", inline=True)
        embed.add_field(name="◈ TEMPO ATIVO", value=f"{horas}h {minutos}m {segundos}s", inline=True)
        embed.add_field(name="◈ ARMAZENAMENTO", value="Upstash" if USANDO_UPSTASH else "Local", inline=True)
        embed.add_field(name="◈ MÓDULOS ATIVOS", value=str(len(self.bot.cogs)), inline=True)
        embed.add_field(name="◈ COMANDOS DO SERVIDOR", value=str(len(comandos)), inline=True)
        if falhas:
            nomes = [str(item.get("cog", "desconhecido")) for item in falhas[:12] if isinstance(item, dict)]
            embed.add_field(
                name=f"⚠️ MÓDULOS COM FALHA ({len(falhas)})",
                value="\n".join(f"• {discord.utils.escape_markdown(nome)}" for nome in nomes)[:1024] or "Falha sem identificação.",
                inline=False,
            )
        else:
            embed.add_field(
                name="✓ INTEGRIDADE DOS MÓDULOS",
                value="Nenhuma falha de carregamento registrada nesta sessão.",
                inline=False,
            )
        embed.add_field(
            name="ℹ️ OBSERVAÇÃO",
            value="O status representa a sessão atual. Use /sistema diagnostico para testar o armazenamento.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="diagnostico", description="Testa a conexão com o armazenamento persistente do bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not USANDO_UPSTASH:
            await interaction.followup.send(
                embed=criar_embed(
                    "⚠️ DIAGNÓSTICO DE ARMAZENAMENTO",
                    "O bot está usando armazenamento local. Dependendo do ambiente de hospedagem, os dados podem não persistir após reinicializações.",
                    cor=COR_AVISO, rodape="NÊMESIS • Diagnóstico", timestamp=True,
                ),
                ephemeral=True,
            )
            return

        try:
            await asyncio.wait_for(verificar_conexao_storage(), timeout=8)
        except asyncio.TimeoutError:
            logging.warning("Diagnóstico manual: timeout ao verificar o armazenamento privado.")
            await interaction.followup.send(
                embed=criar_embed(
                    "⚠️ ARMAZENAMENTO LENTO",
                    "O armazenamento não respondeu em até 8 segundos. Tente novamente; se persistir, consulte os logs do serviço.",
                    cor=COR_AVISO, rodape="NÊMESIS • Diagnóstico", timestamp=True,
                ),
                ephemeral=True,
            )
            return
        except Exception as erro:
            logging.exception("Diagnóstico manual: falha no armazenamento privado.")
            await interaction.followup.send(
                embed=criar_embed(
                    "✕ FALHA NO ARMAZENAMENTO",
                    f"O teste não foi concluído. Tipo do erro: {type(erro).__name__}. Consulte os logs do serviço.",
                    cor=COR_ERRO, rodape="NÊMESIS • Diagnóstico", timestamp=True,
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=criar_embed(
                "✓ ARMAZENAMENTO OPERACIONAL",
                "O teste de conexão foi concluído com sucesso.",
                cor=COR_SUCESSO, rodape="NÊMESIS • Diagnóstico concluído", timestamp=True,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusSistema(bot))
