import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.punicoes import registrar_punicao, historico_punicoes


class Moderacao(commands.Cog):
    """Comandos manuais de moderação, no estilo Carl-bot / Lorrita."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log(self, interaction: discord.Interaction, texto: str):
        from utils.guild_config import get_config
        config = await get_config(interaction.guild.id)
        log_id = config["log_channel_id"]
        if log_id:
            canal = interaction.guild.get_channel(log_id)
            if canal:
                await canal.send(texto)

    @app_commands.command(name="ban", description="Bane um membro do servidor.")
    @app_commands.describe(membro="Membro a ser banido", motivo="Motivo do banimento")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
        await membro.ban(reason=motivo, delete_message_days=0)
        await registrar_punicao(interaction.guild.id, membro.id, "ban", motivo, interaction.user.id)
        await interaction.response.send_message(f"🔨 {membro.mention} foi banido. Motivo: {motivo}")
        await self._log(interaction, f"🔨 {membro.mention} banido por {interaction.user.mention} — {motivo}")

    @app_commands.command(name="kick", description="Expulsa um membro do servidor.")
    @app_commands.describe(membro="Membro a ser expulso", motivo="Motivo da expulsão")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
        await membro.kick(reason=motivo)
        await registrar_punicao(interaction.guild.id, membro.id, "kick", motivo, interaction.user.id)
        await interaction.response.send_message(f"👢 {membro.mention} foi expulso. Motivo: {motivo}")
        await self._log(interaction, f"👢 {membro.mention} expulso por {interaction.user.mention} — {motivo}")

    @app_commands.command(name="mute", description="Silencia um membro por um tempo determinado (em minutos).")
    @app_commands.describe(membro="Membro a silenciar", minutos="Duração em minutos", motivo="Motivo")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membro: discord.Member, minutos: int, motivo: str = "Não especificado"):
        ate = discord.utils.utcnow() + datetime.timedelta(minutes=minutos)
        await membro.timeout(ate, reason=motivo)
        await registrar_punicao(interaction.guild.id, membro.id, "mute", f"{motivo} ({minutos} min)", interaction.user.id)
        await interaction.response.send_message(f"🔇 {membro.mention} foi silenciado por {minutos} min. Motivo: {motivo}")
        await self._log(interaction, f"🔇 {membro.mention} silenciado por {interaction.user.mention} ({minutos} min) — {motivo}")

    @app_commands.command(name="unmute", description="Remove o silenciamento de um membro.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membro: discord.Member):
        await membro.timeout(None)
        await interaction.response.send_message(f"🔊 {membro.mention} não está mais silenciado.")

    @app_commands.command(name="warn", description="Registra um aviso manual para um membro.")
    @app_commands.describe(membro="Membro a avisar", motivo="Motivo do aviso")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membro: discord.Member, motivo: str):
        try:
            await membro.send(f"⚠️ Você recebeu um aviso em **{interaction.guild.name}**: {motivo}")
        except discord.Forbidden:
            pass
        await registrar_punicao(interaction.guild.id, membro.id, "warn", motivo, interaction.user.id)
        await interaction.response.send_message(f"⚠️ {membro.mention} foi avisado. Motivo: {motivo}")
        await self._log(interaction, f"⚠️ {membro.mention} avisado manualmente por {interaction.user.mention} — {motivo}")

    @app_commands.command(name="clear", description="Apaga uma quantidade de mensagens do canal.")
    @app_commands.describe(quantidade="Quantidade de mensagens a apagar (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, quantidade: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        apagadas = await interaction.channel.purge(limit=quantidade)
        await interaction.followup.send(f"🧹 {len(apagadas)} mensagens apagadas.", ephemeral=True)

    @app_commands.command(name="regras", description="Mostra as regras do servidor.")
    async def regras(self, interaction: discord.Interaction):
        from utils.storage import carregar_config
        dados = carregar_config("rules.json")
        embed = discord.Embed(title="📜 Regras do Servidor", color=0x5865F2)
        for regra in dados["regras"]:
            embed.add_field(name=regra["titulo"], value=regra["descricao"], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avisos", description="Mostra os avisos automáticos registrados de um membro.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def avisos(self, interaction: discord.Interaction, membro: discord.Member):
        from utils.storage import carregar
        dados = await carregar("avisos.json", {})
        registros = dados.get(str(interaction.guild.id), {}).get(str(membro.id), {})
        if not registros:
            await interaction.response.send_message(f"{membro.mention} não tem avisos registrados.", ephemeral=True)
            return
        texto = "\n".join(f"• {regra_id}: {qtd}" for regra_id, qtd in registros.items())
        await interaction.response.send_message(f"Avisos de {membro.mention}:\n{texto}", ephemeral=True)

    @app_commands.command(name="punicoes-historico", description="Mostra o histórico de punições de um membro (ou do servidor todo).")
    @app_commands.describe(membro="(Opcional) filtra só esse membro")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def punicoes_historico(self, interaction: discord.Interaction, membro: discord.Member = None):
        registros = await historico_punicoes(interaction.guild.id, membro.id if membro else None)
        if not registros:
            await interaction.response.send_message("Nenhuma punição registrada.", ephemeral=True)
            return

        emojis = {"ban": "🔨", "kick": "👢", "mute": "🔇", "warn": "⚠️", "aviso_automatico": "🤖"}
        linhas = []
        for p in registros:
            quem = f"<@{p['aplicado_por_id']}>" if p["aplicado_por_id"] else "automod"
            linhas.append(f"{emojis.get(p['tipo'], '•')} <@{p['membro_id']}> — **{p['tipo']}** por {quem}: {p['motivo']}")

        titulo = f"📋 Histórico de punições" + (f" — {membro.display_name}" if membro else "")
        embed = discord.Embed(title=titulo, description="\n".join(linhas), color=0xED4245)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- tratamento de erro de permissão ----------
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Você não tem permissão para usar esse comando.", ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderacao(bot))
