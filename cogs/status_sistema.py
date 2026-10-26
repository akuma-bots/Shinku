import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import COR_ERRO, COR_SUCESSO, criar_embed
from utils.storage import USANDO_UPSTASH, verificar_conexao_storage


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
        embed = criar_embed(
            "N̷ÊMESIS ━ STATUS DO SISTEMA",
            cor=COR_SUCESSO if self.bot.is_ready() and not falhas else COR_ERRO,
            rodape="NÊMESIS • Diagnóstico administrativo",
            timestamp=True,
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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="diagnostico", description="Testa a conexão com o armazenamento privado do bot.")
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not USANDO_UPSTASH:
            await interaction.followup.send(
                "⚠️ O bot está usando armazenamento local privado. Os dados podem não persistir após reinicializações.",
                ephemeral=True,
            )
            return

        try:
            await asyncio.wait_for(verificar_conexao_storage(), timeout=8)
        except asyncio.TimeoutError:
            logging.warning("Diagnóstico manual: timeout ao verificar o armazenamento privado.")
            await interaction.followup.send("❌ O armazenamento privado demorou mais de 8 segundos para responder.", ephemeral=True)
            return
        except Exception as erro:
            logging.exception("Diagnóstico manual: falha no armazenamento privado.")
            await interaction.followup.send(
                f"❌ Falha no armazenamento privado: `{type(erro).__name__}`. Confira os logs do Render.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "✅ O armazenamento privado do bot respondeu corretamente.",
            ephemeral=True,
        )


    @app_commands.command(name="canais", description="Audita os canais configurados nos sistemas da NÊMESIS.")
    @app_commands.checks.has_permissions(administrator=True)
    async def canais(self, interaction: discord.Interaction):
        """Confere IDs de canais configurados sem alterar nenhuma configuração."""
        from utils.guild_config import get_config

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        config = await get_config(guild.id)
        destinos = [
            ("Logs gerais", config.get("log_channel_id"), "text"),
            ("Auditoria", config.get("canal_auditoria_id"), "text"),
            ("Regras do AutoMod", 1563995880833421508, "text"),
            ("Infrações do AutoMod", 1563995882234450006, "text"),
            ("Painel de tickets", 1563995881655509059, "text"),
            ("Avaliações de tickets", 1563995881806758056, "text"),
            ("Histórico de tickets", 1563995882540498997, "text"),
            ("Progressão XP", 1563995881315897548, "text"),
            ("Registros de atividade", 1563995881655509054, "text"),
            ("Eventos", config.get("canal_eventos_id"), "text"),
            ("Parcerias", config.get("canal_parcerias_id"), "text"),
            ("Guerras", config.get("canal_guerras_id"), "text"),
            ("Desafios", config.get("canal_desafios_id"), "text"),
            ("Lutas", config.get("canal_lutas_id"), "text"),
            ("Provas PvP", config.get("canal_provas_pvp_id"), "text"),
            ("Ranking", config.get("canal_ranking_id"), "text"),
            ("Missões", config.get("canal_missoes_missao_id"), "text"),
            ("Provas de missões", config.get("canal_provas_missao_id"), "text"),
            ("Contribuições", config.get("canal_missoes_contribuicao_id"), "text"),
            ("Provas de contribuições", config.get("canal_provas_contribuicao_id"), "text"),
            ("Missões especiais", config.get("canal_missoes_especial_id"), "text"),
            ("Provas especiais", config.get("canal_provas_especial_id"), "text"),
            ("Recordes", config.get("canal_recordes_id"), "text"),
            ("Categoria de tickets", config.get("ticket_category_id"), "category"),
        ]

        linhas = []
        por_id = {}
        problemas = []
        validos = 0

        for nome, canal_id, tipo in destinos:
            if not canal_id:
                problemas.append(f"⚠️ **{nome}:** não configurado.")
                continue
            try:
                canal_id = int(canal_id)
            except (TypeError, ValueError):
                problemas.append(f"❌ **{nome}:** ID inválido.")
                continue

            canal = guild.get_channel(canal_id)
            if canal is None:
                try:
                    canal = await guild.fetch_channel(canal_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    problemas.append(f"❌ **{nome}:** canal inacessível ou inexistente (ID: {canal_id}).")
                    continue

            if tipo == "category" and not isinstance(canal, discord.CategoryChannel):
                problemas.append(f"⚠️ **{nome}:** o ID não aponta para uma categoria.")
                continue
            if tipo == "text" and not isinstance(canal, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                problemas.append(f"⚠️ **{nome}:** tipo de canal inesperado.")
                continue

            validos += 1
            linhas.append(f"✅ **{nome}:** {canal.mention} (ID {canal.id})")
            por_id.setdefault(canal.id, []).append(nome)

        for nomes in por_id.values():
            if len(nomes) > 1:
                problemas.append("⚠️ **Destino compartilhado:** " + " / ".join(nomes) + ".")

        embed = criar_embed(
            "NÊMESIS ━ AUDITORIA DE CANAIS",
            cor=COR_ERRO if any(l.startswith("❌") for l in problemas) else COR_SUCESSO,
            rodape="NÊMESIS • Verificação somente leitura",
            timestamp=True,
        )
        embed.description = (
            f"**Verificados:** {len(destinos)} destinos fixos/configurados\n"
            f"**Válidos:** {validos} • **Alertas:** {len(problemas)}\n"
            "A verificação não altera IDs nem cria canais."
        )
        if linhas:
            embed.add_field(name="Canais encontrados", value="\n".join(linhas[:12])[:1024], inline=False)
            if len(linhas) > 12:
                embed.add_field(name="Canais encontrados (continuação)", value="\n".join(linhas[12:24])[:1024], inline=False)
        if problemas:
            embed.add_field(name="Problemas e possíveis duplicações", value="\n".join(problemas[:10])[:1024], inline=False)
            if len(problemas) > 10:
                embed.add_field(name="Alertas adicionais", value="\n".join(problemas[10:20])[:1024], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusSistema(bot))
