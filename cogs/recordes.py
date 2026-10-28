import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import recordes
from utils.apresentacao import COR_PRIMARIA, criar_embed
from utils.guild_config import get_config, set_config

_LOG = logging.getLogger(__name__)

NOMES_CATEGORIA = {
    "vitorias_pvp": ("⚔️", "Vitórias em PvP", "vitória(s)"),
    "xp_total": ("✦", "XP acumulado", "XP"),
    "vitorias_guerra": ("🏰", "Vitórias em guerra", "vitória(s)"),
}


def _categoria(categoria: str):
    return NOMES_CATEGORIA.get(
        categoria,
        ("🏆", categoria.replace("_", " ").title(), ""),
    )


def _valor(valor, unidade: str) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return f"{valor} {unidade}".strip()
    texto = f"{numero:,.2f}" if not numero.is_integer() else f"{int(numero):,}"
    texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{texto} {unidade}".strip()


class Recordes(commands.Cog):
    """Arquivo de recordes e anúncios automáticos da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def anunciar_se_recorde(
        self,
        guild: discord.Guild,
        categoria: str,
        user_id: int,
        valor: float,
    ):
        novo = await recordes.verificar_e_atualizar(
            guild.id, categoria, user_id, valor
        )
        if not novo:
            return

        emoji, nome, unidade = _categoria(categoria)
        config = await get_config(guild.id)
        canal_id = config.get("canal_recordes_id")
        canal = guild.get_channel(canal_id) if canal_id else None
        if not isinstance(canal, discord.TextChannel):
            _LOG.info(
                "Recorde atualizado sem anúncio: canal indisponível (guild=%s).",
                guild.id,
            )
            return

        embed = criar_embed(
            "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOVO RECORDE ・✦",
            f"## {emoji} {discord.utils.escape_markdown(nome)}\n\n"
            f"**Competidor:** <@{user_id}>\n"
            f"**Marca registrada:** {_valor(valor, unidade)}",
            cor=COR_PRIMARIA,
            rodape="NÊMESIS • Arquivo oficial de recordes",
            timestamp=True,
        )
        membro = guild.get_member(user_id)
        if membro:
            embed.set_thumbnail(url=membro.display_avatar.url)
        elif guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        try:
            await canal.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            _LOG.exception(
                "Falha ao anunciar recorde (guild=%s, categoria=%s).",
                guild.id,
                categoria,
            )

    @app_commands.command(
        name="recordes-canal",
        description="Define o canal oficial para anúncios de novos recordes.",
    )
    @app_commands.describe(canal="Canal de texto que receberá os anúncios")
    @app_commands.checks.has_permissions(administrator=True)
    async def recordes_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro da NÊMESIS.",
                ephemeral=True,
            )
            return

        await set_config(interaction.guild.id, canal_recordes_id=canal.id)
        embed = criar_embed(
            "✦・ CENTRAL DE RECORDES — CONFIGURAÇÃO ・✦",
            f"Canal oficial atualizado para {canal.mention}.\n\n"
            "Novas marcas reconhecidas pelos sistemas serão anunciadas aqui.",
            cor=COR_PRIMARIA,
            rodape="NÊMESIS • Configuração concluída",
            timestamp=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="recordes",
        description="Consulta o arquivo atual de recordes competitivos da NÊMESIS.",
    )
    async def recordes_listar(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro da NÊMESIS.",
                ephemeral=True,
            )
            return

        todos = await recordes.obter_todos(interaction.guild.id)
        embed = criar_embed(
            "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — ARQUIVO DE RECORDES ・✦",
            "Marcas competitivas atualmente registradas no servidor.",
            cor=COR_PRIMARIA,
            rodape="NÊMESIS • Estatísticas oficiais",
            timestamp=True,
        )
        if not todos:
            embed.description = (
                "Ainda não há recordes registrados.\n\n"
                "As novas marcas reconhecidas pelos sistemas serão exibidas aqui."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        linhas = []
        for categoria, dado in todos.items():
            if not isinstance(dado, dict) or dado.get("user_id") is None:
                continue
            emoji, nome, unidade = _categoria(categoria)
            linhas.append(
                f"{emoji} **{discord.utils.escape_markdown(nome)}**\n"
                f"└ <@{dado['user_id']}> · **{_valor(dado.get('valor', 0), unidade)}**"
            )

        if not linhas:
            embed.description = (
                "Os dados salvos não contêm recordes válidos para exibição."
            )
        else:
            for inicio in range(0, len(linhas), 5):
                embed.add_field(
                    name="◈ MARCAS REGISTRADAS" if inicio == 0 else "◈ CONTINUAÇÃO",
                    value="\n\n".join(linhas[inicio:inicio + 5])[:1024],
                    inline=False,
                )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Recordes(bot))
