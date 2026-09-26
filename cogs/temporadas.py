import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import temporadas

POSICAO_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}


class Temporadas(commands.Cog):
    """Temporadas competitivas com premiação automática: ao fim do prazo
    configurado, o bot calcula o Top 3 pela pontuação GANHA na temporada, dá
    bônus de XP e o cargo de campeão pro 1º lugar, anuncia no canal
    configurado e já inicia a próxima temporada sozinho."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificar_temporadas.start()

    def cog_unload(self):
        self.verificar_temporadas.cancel()

    async def _anunciar(self, guild: discord.Guild, resultado: dict):
        estado = await temporadas.get_estado(guild.id)
        canal_id = estado.get("canal_id")
        canal = guild.get_channel(canal_id) if canal_id else None
        if not canal:
            return

        linhas = []
        for v in resultado["vencedores"]:
            emoji = POSICAO_EMOJI.get(v["posicao"], "🏅")
            linhas.append(f"{emoji} <@{v['user_id']}> — {int(v['pontos'])} pts (+{v['bonus_xp']} XP de bônus)")

        embed = discord.Embed(
            title=f"🏁 Temporada {resultado['numero_encerrada']} encerrada!",
            description="\n".join(linhas) if linhas else "Ninguém pontuou nessa temporada.",
            color=0xFFD700,
        )
        await canal.send(embed=embed)

        cargo_id = estado.get("cargo_campeao_id")
        if cargo_id and resultado["vencedores"]:
            cargo = guild.get_role(cargo_id)
            campeao_id = resultado["vencedores"][0]["user_id"]
            membro = guild.get_member(campeao_id)
            if cargo:
                for outro in cargo.members:
                    if not membro or outro.id != membro.id:
                        try:
                            await outro.remove_roles(cargo, reason="Fim da temporada — cargo passa pro novo campeão")
                        except discord.Forbidden:
                            pass
                if membro:
                    try:
                        await membro.add_roles(cargo, reason="Campeão da temporada")
                    except discord.Forbidden:
                        pass

    @tasks.loop(hours=1)
    async def verificar_temporadas(self):
        for guild in self.bot.guilds:
            estado = await temporadas.get_estado(guild.id)
            if estado["inicio_timestamp"] is None:
                continue
            if await temporadas.tempo_restante_segundos(guild.id) <= 0:
                resultado = await temporadas.encerrar_temporada(guild.id)
                await self._anunciar(guild, resultado)

    @verificar_temporadas.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="temporada-configurar", description="Configura duração, canal de anúncio, cargo de campeão e bônus de XP da temporada.")
    @app_commands.describe(duracao_dias="Duração de cada temporada em dias", canal="Canal onde o fim da temporada é anunciado",
                            cargo_campeao="Cargo dado ao 1º lugar (opcional)", bonus_ouro="XP de bônus pro 1º lugar",
                            bonus_prata="XP de bônus pro 2º lugar", bonus_bronze="XP de bônus pro 3º lugar")
    @app_commands.checks.has_permissions(administrator=True)
    async def temporada_configurar(self, interaction: discord.Interaction, duracao_dias: int = None,
                                    canal: discord.TextChannel = None, cargo_campeao: discord.Role = None,
                                    bonus_ouro: int = None, bonus_prata: int = None, bonus_bronze: int = None):
        await temporadas.configurar(
            interaction.guild.id,
            duracao_dias=duracao_dias,
            canal_id=canal.id if canal else None,
            cargo_campeao_id=cargo_campeao.id if cargo_campeao else None,
            bonus_ouro=bonus_ouro, bonus_prata=bonus_prata, bonus_bronze=bonus_bronze,
        )
        await interaction.response.send_message("✅ Configuração de temporada atualizada.", ephemeral=True)

    @app_commands.command(name="temporada-encerrar-agora", description="Encerra a temporada atual agora, sem esperar o prazo.")
    @app_commands.checks.has_permissions(administrator=True)
    async def temporada_encerrar_agora(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resultado = await temporadas.encerrar_temporada(interaction.guild.id)
        await self._anunciar(interaction.guild, resultado)
        await interaction.followup.send(f"✅ Temporada {resultado['numero_encerrada']} encerrada.", ephemeral=True)

    @app_commands.command(name="temporada-status", description="Mostra a temporada atual e o Top 3 parcial.")
    async def temporada_status(self, interaction: discord.Interaction):
        estado = await temporadas.get_estado(interaction.guild.id)
        if estado["inicio_timestamp"] is None:
            await interaction.response.send_message("Nenhuma temporada configurada ainda. Use `/temporada-configurar`.", ephemeral=True)
            return

        restante = await temporadas.tempo_restante_segundos(interaction.guild.id)
        dias_restantes = int(restante // 86400)
        horas_restantes = int((restante % 86400) // 3600)

        top3 = await temporadas.top_da_temporada(interaction.guild.id, limite=3)
        linhas = [f"{POSICAO_EMOJI.get(i+1, '🏅')} <@{uid}> — {int(pontos)} pts" for i, (uid, pontos) in enumerate(top3)]

        embed = discord.Embed(
            title=f"🏆 Temporada {estado['numero_atual']}",
            description=(f"Termina em **{dias_restantes}d {horas_restantes}h**\n\n" +
                         ("\n".join(linhas) if linhas else "Ninguém pontuou ainda nessa temporada.")),
            color=0xFFD700,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Temporadas(bot))