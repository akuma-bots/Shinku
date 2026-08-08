import time
import discord
from discord.ext import commands
from utils.guild_config import get_config

JANELA_SEGUNDOS = 10
LIMITE_ENTRADAS = 6          # X membros entrando na janela = suspeita de raid
IDADE_MINIMA_CONTA_HORAS = 24  # contas mais novas que isso, durante um raid, são expulsas


class AntiRaid(commands.Cog):
    """Detecta picos anormais de entrada de membros (possível raid/ataque em massa),
    avisa a equipe de suporte e expulsa automaticamente contas muito novas
    que entrarem durante a janela de suspeita."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._entradas_por_guild = {}   # guild_id -> [timestamps]
        self._raid_ativo = {}           # guild_id -> bool

    async def _canal_logs(self, guild: discord.Guild):
        config = await get_config(guild.id)
        log_id = config["log_channel_id"]
        return guild.get_channel(log_id) if log_id else None

    async def _mencao_suporte(self, guild: discord.Guild) -> str:
        config = await get_config(guild.id)
        cargo_id = config["support_role_id"]
        return f"<@&{cargo_id}>" if cargo_id else "Equipe de suporte"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        agora = time.time()
        guild_id = member.guild.id

        historico = self._entradas_por_guild.setdefault(guild_id, [])

        # se já fazia mais de 30s desde a última entrada, o raid anterior (se havia) acabou
        if historico and agora - historico[-1] > 30:
            self._raid_ativo[guild_id] = False

        historico.append(agora)
        self._entradas_por_guild[guild_id] = [t for t in historico if agora - t <= JANELA_SEGUNDOS]

        raid_suspeito = len(self._entradas_por_guild[guild_id]) >= LIMITE_ENTRADAS

        if raid_suspeito and not self._raid_ativo.get(guild_id):
            self._raid_ativo[guild_id] = True
            canal = await self._canal_logs(member.guild)
            if canal:
                await canal.send(
                    f"🚨 {await self._mencao_suporte(member.guild)} **Possível raid detectado!** "
                    f"{len(self._entradas_por_guild[guild_id])} membros entraram em menos de {JANELA_SEGUNDOS}s. "
                    f"Contas com menos de {IDADE_MINIMA_CONTA_HORAS}h de criação serão expulsas automaticamente "
                    f"enquanto durar o pico de entradas."
                )

        if self._raid_ativo.get(guild_id):
            idade_conta = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
            if idade_conta < IDADE_MINIMA_CONTA_HORAS:
                try:
                    await member.kick(reason="Anti-raid: conta muito nova durante pico de entradas suspeito.")
                    canal = await self._canal_logs(member.guild)
                    if canal:
                        await canal.send(f"👢 {member.mention} expulso automaticamente (anti-raid, conta nova).")
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
