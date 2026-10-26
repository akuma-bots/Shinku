import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

GUILD_NEMESIS_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
COR_NEMESIS = 0xB3132B
CONCORRENCIA_DMS = 4


class NotasAtualizacao(commands.Cog):
    """Publica notas de atualização da NÊMESIS por mensagem direta aos membros."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._envios_em_andamento: set[int] = set()

    @app_commands.command(
        name="nota-atualizacao",
        description="Envia as notas de uma atualização por DM aos membros da NÊMESIS.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        versao="Versão ou identificação da atualização (ex.: Update 2.4)",
        resumo="Resumo curto do objetivo desta atualização.",
        novidades="Lista do que mudou ou foi adicionado. Separe cada novidade por uma nova linha.",
        correcoes="Correções e melhorias adicionais (opcional).",
    )
    async def nota_atualizacao(
        self,
        interaction: discord.Interaction,
        versao: app_commands.Range[str, 1, 80],
        resumo: app_commands.Range[str, 1, 500],
        novidades: app_commands.Range[str, 1, 3500],
        correcoes: app_commands.Range[str, 1, 1500] | None = None,
    ):
        if interaction.guild_id != GUILD_NEMESIS_ID or interaction.guild is None:
            await interaction.response.send_message(
                "Este comando está disponível apenas no servidor oficial da NÊMESIS.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Somente administradores podem publicar notas de atualização.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild.id in self._envios_em_andamento:
            await interaction.response.send_message(
                "Já existe um envio de notas de atualização em andamento. Aguarde a conclusão.",
                ephemeral=True,
            )
            return

        self._envios_em_andamento.add(guild.id)
        await interaction.response.defer(ephemeral=True, thinking=True)

        linhas = [linha.strip() for linha in novidades.splitlines() if linha.strip()]
        if not linhas:
            self._envios_em_andamento.discard(guild.id)
            await interaction.followup.send(
                "Informe pelo menos uma novidade, cada uma em uma linha.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
            description=(
                f"⟡・ **{discord.utils.escape_markdown(versao)}**\n"
                f"{discord.utils.escape_markdown(resumo)}"
            ),
            color=COR_NEMESIS,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="✦ O QUE HÁ DE NOVO",
            value="\n".join(f"➜ {discord.utils.escape_markdown(item)}" for item in linhas),
            inline=False,
        )
        if correcoes and correcoes.strip():
            correcoes_linhas = [
                linha.strip() for linha in correcoes.splitlines() if linha.strip()
            ]
            valor = "\n".join(
                f"✓ {discord.utils.escape_markdown(item)}" for item in correcoes_linhas
            )
            # Limita o campo ao máximo aceito pelo Discord.
            embed.add_field(
                name="⚙️ CORREÇÕES E MELHORIAS",
                value=valor[:1024],
                inline=False,
            )
        embed.add_field(
            name="⟡・ ACOMPANHE AS NOVIDADES",
            value=(
                "Esta mensagem resume as mudanças desta versão. "
                "Consulte os canais oficiais da NÊMESIS para comunicados complementares."
            ),
            inline=False,
        )
        embed.set_footer(text="NÊMESIS • Update Notes • Comunicado oficial")

        membros = [membro for membro in guild.members if not membro.bot]
        sucesso = 0
        falhas = 0
        bloqueados = 0
        semaforo = asyncio.Semaphore(CONCORRENCIA_DMS)

        async def enviar(membro: discord.Member):
            nonlocal sucesso, falhas, bloqueados
            async with semaforo:
                try:
                    await membro.send(embed=embed)
                    sucesso += 1
                except discord.Forbidden:
                    bloqueados += 1
                except discord.HTTPException:
                    falhas += 1
                    logger.warning(
                        "Falha ao enviar nota de atualização por DM (guild=%s, member=%s).",
                        guild.id,
                        membro.id,
                        exc_info=True,
                    )
                await asyncio.sleep(0.35)

        try:
            await asyncio.gather(*(enviar(membro) for membro in membros))
        finally:
            self._envios_em_andamento.discard(guild.id)

        logger.info(
            "Notas de atualização enviadas: guild=%s versão=%s sucesso=%s bloqueados=%s falhas=%s",
            guild.id,
            versao,
            sucesso,
            bloqueados,
            falhas,
        )
        await interaction.followup.send(
            f"**Notas de atualização processadas — {discord.utils.escape_markdown(versao)}**\n"
            f"• Entregues: **{sucesso}**\n"
            f"• DMs fechadas ou bloqueadas: **{bloqueados}**\n"
            f"• Outras falhas: **{falhas}**\n"
            f"• Membros considerados: **{len(membros)}**\n\n"
            "O Discord não permite entregar mensagens a membros que bloqueiam DMs do servidor.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
