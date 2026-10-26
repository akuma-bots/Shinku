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


def _adicionar_campos_em_blocos(embed: discord.Embed, titulo: str, itens: list[str], prefixo: str):
    """Divide listas em campos compatíveis com o limite de 1.024 caracteres do Discord."""
    blocos: list[str] = []
    atual = ""
    for item in itens:
        linha = f"{prefixo} {discord.utils.escape_markdown(item)}"
        if len(linha) > 1000:
            linha = linha[:997] + "..."
        candidato = f"{atual}\n{linha}" if atual else linha
        if len(candidato) > 1000:
            blocos.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual:
        blocos.append(atual)
    for indice, bloco in enumerate(blocos):
        nome = titulo if indice == 0 else f"{titulo} (continuação {indice + 1})"
        embed.add_field(name=nome[:256], value=bloco, inline=False)


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
        novidades="O que mudou ou foi adicionado. Separe cada item por uma nova linha.",
        correcoes="Correções e melhorias adicionais (opcional).",
    )
    async def nota_atualizacao(
        self,
        interaction: discord.Interaction,
        versao: str,
        resumo: str,
        novidades: str,
        correcoes: str | None = None,
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

        if not versao.strip() or len(versao) > 80 or not resumo.strip() or len(resumo) > 500:
            await interaction.response.send_message(
                "A versão deve ter até 80 caracteres e o resumo até 500 caracteres.",
                ephemeral=True,
            )
            return
        if not novidades.strip() or len(novidades) > 3500:
            await interaction.response.send_message(
                "Informe as novidades (até 3.500 caracteres), uma por linha.",
                ephemeral=True,
            )
            return
        if correcoes and len(correcoes) > 1500:
            await interaction.response.send_message(
                "As correções podem ter até 1.500 caracteres.",
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

        linhas = [linha.strip() for linha in novidades.splitlines() if linha.strip()]
        if not linhas:
            await interaction.response.send_message(
                "Informe pelo menos uma novidade, cada uma em uma linha.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
            description=(
                f"⟡・ **{discord.utils.escape_markdown(versao.strip())}**\n"
                f"{discord.utils.escape_markdown(resumo.strip())}"
            ),
            color=COR_NEMESIS,
            timestamp=datetime.now(timezone.utc),
        )
        _adicionar_campos_em_blocos(embed, "✦ O QUE HÁ DE NOVO", linhas, "➜")

        if correcoes and correcoes.strip():
            correcoes_linhas = [
                linha.strip() for linha in correcoes.splitlines() if linha.strip()
            ]
            _adicionar_campos_em_blocos(
                embed, "⚙️ CORREÇÕES E MELHORIAS", correcoes_linhas, "✓"
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
        await interaction.response.defer(ephemeral=True, thinking=True)
        self._envios_em_andamento.add(guild.id)
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
            f"**Notas de atualização processadas — {discord.utils.escape_markdown(versao.strip())}**\n"
            f"• Entregues: **{sucesso}**\n"
            f"• DMs fechadas ou bloqueadas: **{bloqueados}**\n"
            f"• Outras falhas: **{falhas}**\n"
            f"• Membros considerados: **{len(membros)}**\n\n"
            "O Discord não permite entregar mensagens a membros que bloqueiam DMs do servidor.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
