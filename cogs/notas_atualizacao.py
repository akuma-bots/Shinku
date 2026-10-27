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
SEND_DELAY = 1.0
MAX_RETRIES = 3


def _chunks(lines: list[str], prefix: str, limit: int = 950) -> list[str]:
    chunks: list[str] = []
    current = ""
    for raw in lines:
        safe = discord.utils.escape_markdown(raw.strip())
        if not safe:
            continue
        line = f"{prefix} {safe}"
        if len(line) > limit:
            line = line[: limit - 3] + "..."
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _adicionar_secao(embed: discord.Embed, titulo: str, linhas: list[str], prefixo: str):
    for index, bloco in enumerate(_chunks(linhas, prefixo)):
        nome = titulo if index == 0 else f"{titulo} • continuação {index + 1}"
        embed.add_field(name=nome[:256], value=bloco or "—", inline=False)


async def _enviar_nota(member: discord.Member, embed: discord.Embed) -> str:
    """Retorna enviada, bloqueada ou falha após tentativas limitadas."""
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            await member.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return "enviada"
        except (discord.Forbidden, discord.NotFound):
            return "bloqueada"
        except discord.HTTPException as erro:
            if erro.status and 400 <= erro.status < 500 and erro.status != 429:
                return "bloqueada"
            if tentativa == MAX_RETRIES:
                log.warning("Falha ao enviar nota (guild=%s, member=%s).", member.guild.id, member.id, exc_info=True)
                return "falha"
            espera = min(2 ** (tentativa - 1), 8)
            retry_after = getattr(erro, "retry_after", None)
            if isinstance(retry_after, (int, float)):
                espera = max(espera, min(float(retry_after), 30))
            await asyncio.sleep(espera)
        except (asyncio.TimeoutError, OSError, discord.ConnectionClosed):
            if tentativa == MAX_RETRIES:
                log.warning("Falha de conexão ao enviar nota (guild=%s, member=%s).", member.guild.id, member.id, exc_info=True)
                return "falha"
            await asyncio.sleep(min(2 ** (tentativa - 1), 8))
    return "falha"


class NotasAtualizacao(commands.Cog):
    """Prévia e envio explícito de notas de atualização para membros humanos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sending: set[int] = set()

    @app_commands.command(name="nota-atualizacao", description="Preparar, visualizar e enviar notas de atualização.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        versao="Versão ou identificador da atualização (até 80 caracteres).",
        resumo="Resumo curto do que mudou (até 450 caracteres).",
        novidades="Novidades, uma por linha.",
        correcoes="Correções e melhorias, uma por linha (opcional).",
        confirmar_envio="Marque verdadeiro somente depois de revisar a prévia.",
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
            await interaction.response.send_message("Já existe um envio de notas em andamento. Aguarde a conclusão.", ephemeral=True)
            return

        versao, resumo, novidades = versao.strip(), resumo.strip(), novidades.strip()
        correcoes = (correcoes or "").strip()
        if not versao or len(versao) > 80 or not resumo or len(resumo) > 450:
            await interaction.response.send_message("Informe uma versão (até 80 caracteres) e um resumo (até 450).", ephemeral=True)
            return
        if not novidades or len(novidades) > 3000 or len(correcoes) > 1200:
            await interaction.response.send_message("Novidades: até 3.000 caracteres; correções: até 1.200.", ephemeral=True)
            return

        updates = [line.strip().lstrip("-•* ").strip() for line in novidades.splitlines() if line.strip()]
        fixes = [line.strip().lstrip("-•* ").strip() for line in correcoes.splitlines() if line.strip()]
        if not updates or any(not item for item in updates):
            await interaction.response.send_message("Inclua pelo menos uma novidade válida, uma por linha.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
            description=f"⟡・ **{discord.utils.escape_markdown(versao)}**\n{discord.utils.escape_markdown(resumo)}",
            color=COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        _adicionar_secao(embed, "✦ NOVIDADES", updates, "➜")
        if fixes:
            _adicionar_secao(embed, "⚙ CORREÇÕES E MELHORIAS", fixes, "✓")
        embed.set_footer(text="NÊMESIS • Notas oficiais de atualização")

        if not confirmar_envio:
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
                count_text = str(len(membros))
            except discord.HTTPException:
                log.exception("Falha ao contar membros para prévia das notas.")
                count_text = "não foi possível confirmar"
            preview = embed.copy()
            preview.add_field(
                name="PRÉVIA — NENHUMA DM ENVIADA",
                value=f"Destinatários humanos estimados: **{count_text}**.\nRevise o conteúdo e execute novamente com confirmar_envio verdadeiro para enviar.",
                inline=False,
            )
            await interaction.followup.send("Prévia pronta. Nenhuma mensagem foi enviada.", embed=preview, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return

        self._sending.add(guild.id)
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
        except discord.HTTPException:
            self._sending.discard(guild.id)
            log.exception("Falha ao carregar membros para envio das notas.")
            mensagem = "Não consegui carregar a lista completa de membros. Nenhuma nota foi enviada."
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)
            return

        entregues = bloqueadas = falhas = 0
        try:
            total = len(membros)
            for index, member in enumerate(membros, start=1):
                resultado = await _enviar_nota(member, embed)
                if resultado == "enviada":
                    entregues += 1
                elif resultado == "bloqueada":
                    bloqueadas += 1
                else:
                    falhas += 1
                if index % 25 == 0 and index < total:
                    try:
                        await interaction.edit_original_response(content=f"**Enviando notas {versao}**\nProcessados: **{index}/{total}** · Entregues: **{entregues}** · Bloqueadas: **{bloqueadas}** · Falhas: **{falhas}**")
                    except discord.HTTPException:
                        log.debug("Não foi possível atualizar o progresso do envio.")
                await asyncio.sleep(SEND_DELAY)
        finally:
            self._sending.discard(guild.id)

        log.info("Notas de atualização concluídas (guild=%s, versao=%s, total=%s, entregues=%s, bloqueadas=%s, falhas=%s, autor=%s).", guild.id, versao, len(membros), entregues, bloqueadas, falhas, interaction.user.id)
        await interaction.followup.send(
            f"**Notas processadas — {discord.utils.escape_markdown(versao)}**\n"
            f"• Membros humanos: **{len(membros)}**\n• Entregues: **{entregues}**\n• DMs bloqueadas/indisponíveis: **{bloqueadas}**\n• Falhas após tentativas: **{falhas}**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
