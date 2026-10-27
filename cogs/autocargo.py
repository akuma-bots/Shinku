import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands
from utils.guild_config import (
    get_config,
    definir_canal_cargo_automatico,
    remover_canal_cargo_automatico,
)

_LOG = logging.getLogger(__name__)
_AUTO_ROLE_LOCK = asyncio.Lock()


def _cargo_atribuivel(guild, cargo) -> bool:
    bot_member = getattr(guild, "me", None)
    if bot_member is None:
        return False
    permissoes = getattr(bot_member, "guild_permissions", None)
    if permissoes is None or not getattr(permissoes, "manage_roles", False):
        return False
    try:
        return not cargo.is_default() and not cargo.managed and cargo < bot_member.top_role
    except (AttributeError, TypeError):
        return False


class CargoAutomatico(commands.Cog):
    """Canais 'administrados' pelo bot: qualquer mensagem postada ali
    (texto, print, comprovante etc) dá automaticamente um cargo escolhido
    ao membro que postou — útil pra verificação, comprovação de compra,
    aceite de regras e afins. Configuração é por servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Cargos-base concedidos automaticamente a novos membros da NÊMESIS.
    GUILD_ID_CARGOS_ENTRADA = 1563995879981981817
    CARGOS_ENTRADA = (
        1563995879990624371,
        1563995879981981825,
        1563995879981981818,
    )

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        """Atribui os três cargos-base quando alguém entra no servidor oficial."""
        if membro.guild.id != self.GUILD_ID_CARGOS_ENTRADA or membro.bot:
            return

        cargos = []
        ausentes = []
        for cargo_id in self.CARGOS_ENTRADA:
            cargo = membro.guild.get_role(cargo_id)
            if cargo is None:
                ausentes.append(cargo_id)
                continue
            if cargo not in membro.roles:
                if not _cargo_atribuivel(membro.guild, cargo):
                    _LOG.warning(
                        "Cargo de entrada não atribuível (guild=%s, member=%s, role=%s). "
                        "Verifique Gerenciar cargos e a hierarquia.",
                        membro.guild.id, membro.id, cargo.id,
                    )
                    continue
                cargos.append(cargo)

        if ausentes:
            _LOG.error(
                "Cargos de entrada não encontrados no servidor (guild=%s, ids=%s).",
                membro.guild.id, ausentes,
            )
        if not cargos:
            return

        try:
            await membro.add_roles(*cargos, reason="Atribuição automática de cargos ao entrar na NÊMESIS.")
            _LOG.info(
                "Cargos de entrada atribuídos (guild=%s, member=%s, roles=%s).",
                membro.guild.id, membro.id, [cargo.id for cargo in cargos],
            )
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception(
                "Falha ao atribuir cargos de entrada (guild=%s, member=%s).",
                membro.guild.id, membro.id,
            )

    @app_commands.command(
        name="definir-canal-cargo",
        description="Define um canal onde postar qualquer mensagem dá um cargo automático.",
    )
    @app_commands.describe(canal="Canal que vai dar o cargo", cargo="Cargo que a pessoa recebe ao postar ali")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def definir_canal_cargo(self, interaction: discord.Interaction, canal: discord.TextChannel, cargo: discord.Role):
        if not _cargo_atribuivel(interaction.guild, cargo):
            await interaction.response.send_message(
                "⚠️ Não consigo atribuir esse cargo. Confira se tenho a permissão **Gerenciar cargos** "
                "e se o cargo escolhido é atribuível e está abaixo do meu cargo mais alto.",
                ephemeral=True,
            )
            return

        await definir_canal_cargo_automatico(interaction.guild.id, canal.id, cargo.id)
        await interaction.response.send_message(
            f"✅ A partir de agora, quem postar qualquer mensagem (texto ou print) em {canal.mention} "
            f"recebe automaticamente o cargo {cargo.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="remover-canal-cargo",
        description="Remove o cargo automático de um canal.",
    )
    @app_commands.describe(canal="Canal que vai deixar de dar cargo automático")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remover_canal_cargo(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await remover_canal_cargo_automatico(interaction.guild.id, canal.id)
        await interaction.response.send_message(f"🔒 {canal.mention} não dá mais cargo automático.", ephemeral=True)

    @app_commands.command(
        name="canais-cargo-automatico",
        description="Lista os canais que dão cargo automático neste servidor.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def canais_cargo_automatico(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        mapa = config["canais_cargo_automatico"]

        if not mapa:
            await interaction.response.send_message("Nenhum canal de cargo automático configurado ainda.", ephemeral=True)
            return

        linhas = [f"<#{canal_id}> → <@&{cargo_id}>" for canal_id, cargo_id in mapa.items()]
        embed = discord.Embed(
            title="📋 Canais com cargo automático",
            description="\n".join(linhas),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await get_config(message.guild.id)
        cargo_id = config["canais_cargo_automatico"].get(str(message.channel.id))
        if not cargo_id:
            return

        cargo = message.guild.get_role(cargo_id)
        if not cargo:
            return

        membro = message.author
        if cargo in membro.roles:
            return  # já tem o cargo, não faz nada

        async with _AUTO_ROLE_LOCK:
            # Outro evento pode ter atribuído o cargo enquanto este aguardava o lock.
            membro = message.guild.get_member(message.author.id) or membro
            if cargo in membro.roles:
                return
            if not _cargo_atribuivel(message.guild, cargo):
                _LOG.warning(
                    "Cargo automático não atribuível (guild=%s, channel=%s, role=%s).",
                    message.guild.id, message.channel.id, cargo.id,
                )
                return
            try:
                await membro.add_roles(cargo, reason=f"Postou em {message.channel.name} (cargo automático).")
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception(
                    "Falha ao atribuir cargo automático (guild=%s, member=%s, role=%s).",
                    message.guild.id, membro.id, cargo.id,
                )
                canal_logs_id = config.get("log_channel_id")
                canal_logs = message.guild.get_channel(canal_logs_id) if canal_logs_id else None
                if canal_logs:
                    try:
                        await canal_logs.send(
                            f"⚠️ Não consegui atribuir o cargo automático (membro ID: {membro.id}, cargo ID: {cargo.id}).",
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    except discord.HTTPException:
                        _LOG.warning("Falha ao enviar aviso de cargo automático (guild=%s).", message.guild.id)
                return

        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(CargoAutomatico(bot))
