import json
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import lideranca_only, membro_tem_lideranca

GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
CAMINHO_RELEASE = Path(__file__).resolve().parent.parent / "config" / "novidades.json"


class NotasAtualizacao(commands.Cog):
    """Consulta somente leitura da release automática; não envia DMs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="notas-atualizacao",
        description="Consultar a nota de atualização programada da NÊMESIS.",
    )
    @app_commands.guild_only()
    @lideranca_only()
    async def notas_atualizacao(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID or interaction.guild is None:
            await interaction.response.send_message(
                "Comando exclusivo da NÊMESIS.", ephemeral=True
            )
            return
        if (
            not isinstance(interaction.user, discord.Member)
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "Somente a liderança autorizada pode consultar este painel.",
                ephemeral=True,
            )
            return

        try:
            release = json.loads(CAMINHO_RELEASE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            await interaction.response.send_message(
                "Não foi possível carregar a nota configurada. Nenhuma DM foi enviada.",
                ephemeral=True,
            )
            return

        if not isinstance(release, dict):
            await interaction.response.send_message(
                "O manifesto de atualização está inválido. Nenhuma DM foi enviada.",
                ephemeral=True,
            )
            return

        titulo = str(release.get("titulo") or "Atualização da NÊMESIS")[:200]
        mensagem = str(release.get("mensagem") or "Sem descrição.")[:3500]
        data = str(release.get("data_atualizacao") or "Não informada")[:30]
        hora = str(release.get("hora_atualizacao") or "Não informado")[:20]
        tipo = str(release.get("tipo") or "Atualização")[:100]
        release_id = str(release.get("release_id") or "Não informado")[:100]

        embed = discord.Embed(
            title=f"✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — {titulo} ・✦",
            description=mensagem,
            color=0xB3132B,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="◈ CATEGORIA", value=tipo, inline=True)
        embed.add_field(name="◈ DATA", value=data, inline=True)
        embed.add_field(name="◈ HORÁRIO", value=hora, inline=True)
        embed.set_footer(text=f"NÊMESIS • Release {release_id}")

        usuario = self.bot.user
        avatar = getattr(getattr(usuario, "display_avatar", None), "url", None)
        banner = getattr(getattr(usuario, "banner", None), "url", None)
        banner_servidor = getattr(getattr(interaction.guild, "banner", None), "url", None)
        if avatar:
            embed.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 • NOTAS OFICIAIS", icon_url=avatar)
            embed.set_thumbnail(url=avatar)
        if banner or banner_servidor:
            embed.set_image(url=banner or banner_servidor)

        await interaction.response.send_message(
            "Prévia somente leitura da próxima nota automática. Este comando não dispara mensagens; o envio é controlado exclusivamente pelo sistema automático.",
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
