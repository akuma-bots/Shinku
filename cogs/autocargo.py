import discord
from discord import app_commands
from discord.ext import commands
from utils.guild_config import (
    get_config,
    definir_canal_cargo_automatico,
    remover_canal_cargo_automatico,
)


class CargoAutomatico(commands.Cog):
    """Canais 'administrados' pelo bot: qualquer mensagem postada ali
    (texto, print, comprovante etc) dá automaticamente um cargo escolhido
    ao membro que postou — útil pra verificação, comprovação de compra,
    aceite de regras e afins. Configuração é por servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="definir-canal-cargo",
        description="Define um canal onde postar qualquer mensagem dá um cargo automático.",
    )
    @app_commands.describe(canal="Canal que vai dar o cargo", cargo="Cargo que a pessoa recebe ao postar ali")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def definir_canal_cargo(self, interaction: discord.Interaction, canal: discord.TextChannel, cargo: discord.Role):
        if cargo >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "⚠️ Esse cargo está acima (ou igual) ao meu cargo mais alto — eu não vou conseguir atribuir ele. "
                "Suba meu cargo na lista de cargos do servidor, acima do cargo escolhido, e tente de novo.",
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

        try:
            await membro.add_roles(cargo, reason=f"Postou em {message.channel.name} (cargo automático).")
        except discord.Forbidden:
            canal_logs_id = config["log_channel_id"]
            canal_logs = message.guild.get_channel(canal_logs_id) if canal_logs_id else None
            if canal_logs:
                await canal_logs.send(
                    f"⚠️ Não consegui dar o cargo {cargo.mention} para {membro.mention} "
                    f"(faltam permissões ou o cargo está acima do meu)."
                )
            return

        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(CargoAutomatico(bot))
