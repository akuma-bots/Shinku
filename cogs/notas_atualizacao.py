import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)
GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
COLOR = 0xB3132B
SEND_DELAY = 0.4


def add_lines(embed: discord.Embed, title: str, lines: list[str], prefix: str):
    chunks = []
    current = ""
    for raw in lines:
        line = f"{prefix} {discord.utils.escape_markdown(raw)}"
        if len(line) > 950:
            line = line[:947] + "..."
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 950:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks):
        embed.add_field(name=(title if index == 0 else f"{title} (continuação {index + 1})")[:256], value=chunk or "—", inline=False)


class NotasAtualizacao(commands.Cog):
    """Publica notas de atualização por DM, com prévia e confirmação explícita."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sending: set[int] = set()

    @app_commands.command(name="nota-atualizacao", description="Preparar e enviar notas de atualização por DM.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        versao="Versão ou identificação da atualização.",
        resumo="Resumo curto da atualização.",
        novidades="Novidades, uma por linha.",
        correcoes="Correções adicionais, uma por linha (opcional).",
        confirmar_envio="Defina como verdadeiro para confirmar o envio a todos os membros humanos.",
    )
    async def nota_atualizacao(
        self,
        interaction: discord.Interaction,
        versao: str,
        resumo: str,
        novidades: str,
        correcoes: str | None = None,
        confirmar_envio: bool = False,
    ):
        guild = interaction.guild
        if guild is None or interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Comando exclusivo da NÊMESIS.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Somente administradores podem usar este comando.", ephemeral=True)
            return
        if guild.id in self._sending:
            await interaction.response.send_message("Já existe um envio em andamento. Aguarde.", ephemeral=True)
            return
        if not versao.strip() or len(versao) > 80 or not resumo.strip() or len(resumo) > 450:
            await interaction.response.send_message("Informe uma versão (até 80 caracteres) e um resumo (até 450).", ephemeral=True)
            return
        if not novidades.strip() or len(novidades) > 3000 or (correcoes and len(correcoes) > 1200):
            await interaction.response.send_message("Novidades: até 3.000 caracteres; correções: até 1.200.", ephemeral=True)
            return
        updates = [line.strip() for line in novidades.splitlines() if line.strip()]
        fixes = [line.strip() for line in (correcoes or "").splitlines() if line.strip()]
        if not updates:
            await interaction.response.send_message("Inclua pelo menos uma novidade.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
            description=f"⟡・ **{discord.utils.escape_markdown(versao.strip())}**\n{discord.utils.escape_markdown(resumo.strip())}",
            color=COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        add_lines(embed, "✦ NOVIDADES", updates, "➜")
        if fixes:
            add_lines(embed, "⚙️ CORREÇÕES E MELHORIAS", fixes, "✓")
        embed.set_footer(text="NÊMESIS • Comunicado oficial de atualização")

        if not confirmar_envio:
            count = sum(1 for member in guild.members if not member.bot)
            preview = embed.copy()
            preview.add_field(name="PRÉVIA — NENHUMA DM ENVIADA", value=f"Destinatários considerados: {count}. Execute novamente com confirmar_envio verdadeiro para disparar.", inline=False)
            await interaction.response.send_message(
                "Esta é uma prévia. Nenhuma mensagem foi enviada. Confirme explicitamente antes do envio em massa.",
                embed=preview,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        # Marcar antes do primeiro await evita que duas interações iniciem
        # envios em massa simultâneos para o mesmo servidor.
        self._sending.add(guild.id)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            self._sending.discard(guild.id)
            raise

        delivered = blocked = failed = 0
        members = [member for member in guild.members if not member.bot]
        try:
            for member in members:
                try:
                    await member.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                    delivered += 1
                except discord.Forbidden:
                    blocked += 1
                except discord.HTTPException:
                    failed += 1
                    log.warning("Falha na DM de atualização (guild=%s, member=%s).", guild.id, member.id, exc_info=True)
                await asyncio.sleep(SEND_DELAY)
        finally:
            self._sending.discard(guild.id)

        log.info("Notas processadas: guild=%s version=%s delivered=%s blocked=%s failed=%s total=%s", guild.id, versao, delivered, blocked, failed, len(members))
        await interaction.followup.send(
            f"Notas processadas — {discord.utils.escape_markdown(versao.strip())}\n"
            f"• Entregues: {delivered}\n• DMs bloqueadas: {blocked}\n• Falhas: {failed}\n• Membros considerados: {len(members)}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
