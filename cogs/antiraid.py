import logging
import time

import discord
from discord.ext import commands

from utils.guild_config import get_config


logger = logging.getLogger(__name__)

JANELA_SEGUNDOS = 10
LIMITE_ENTRADAS = 6
IDADE_MINIMA_CONTA_HORAS = 24


class AntiRaid(commands.Cog):
    """Detecta picos de entrada e aplica proteção limitada contra contas novas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._entradas_por_guild = {}
        self._raid_ativo = {}

    @staticmethod
    def _alvo_elegivel(member: discord.Member) -> bool:
        """Nunca expulsa bots ou membros com privilégios administrativos."""
        if member.bot or member.id == member.guild.owner_id:
            return False
        permissoes = member.guild_permissions
        if permissoes.administrator or permissoes.manage_guild:
            return False
        return True

    async def _canal_logs(self, guild: discord.Guild):
        try:
            config = await get_config(guild.id)
            log_id = config.get("log_channel_id")
            if not log_id:
                return None
            canal = guild.get_channel(int(log_id))
            if canal is None:
                try:
                    canal = await self.bot.fetch_channel(int(log_id))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    return None
            return canal if callable(getattr(canal, "send", None)) else None
        except Exception:
            logger.exception("Falha ao resolver canal de logs do anti-raid (guild=%s).", guild.id)
            return None

    async def _avisar(self, guild: discord.Guild, texto: str, mencionar_suporte: bool = False):
        canal = await self._canal_logs(guild)
        if canal is None:
            return
        try:
            if mencionar_suporte:
                config = await get_config(guild.id)
                cargo_id = config.get("support_role_id")
                prefixo = f"<@&{cargo_id}> " if cargo_id else ""
                await canal.send(
                    prefixo + texto,
                    allowed_mentions=discord.AllowedMentions(
                        roles=bool(cargo_id), users=False, everyone=False,
                    ),
                )
            else:
                await canal.send(
                    texto,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Não foi possível enviar aviso anti-raid (guild=%s, channel=%s).", guild.id, getattr(canal, "id", None))
        except Exception:
            logger.exception("Erro inesperado ao enviar aviso anti-raid (guild=%s).", guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        agora = time.time()
        guild_id = member.guild.id
        historico = self._entradas_por_guild.setdefault(guild_id, [])

        if historico and agora - historico[-1] > 30:
            self._raid_ativo[guild_id] = False

        historico.append(agora)
        recentes = [timestamp for timestamp in historico if agora - timestamp <= JANELA_SEGUNDOS]
        self._entradas_por_guild[guild_id] = recentes

        raid_suspeito = len(recentes) >= LIMITE_ENTRADAS
        if raid_suspeito and not self._raid_ativo.get(guild_id):
            self._raid_ativo[guild_id] = True
            await self._avisar(
                member.guild,
                f"🚨 **Possível raid detectado!** {len(recentes)} membros entraram em menos de "
                f"{JANELA_SEGUNDOS}s. Contas com menos de {IDADE_MINIMA_CONTA_HORAS}h serão avaliadas "
                "pela proteção automática durante o pico.",
                mencionar_suporte=True,
            )

        if not self._raid_ativo.get(guild_id) or not self._alvo_elegivel(member):
            return

        idade_conta = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
        if idade_conta >= IDADE_MINIMA_CONTA_HORAS:
            return

        try:
            await member.kick(reason="Anti-raid: conta muito nova durante pico de entradas suspeito.")
            await self._avisar(
                member.guild,
                f"🛡️ Um membro com conta criada há menos de {IDADE_MINIMA_CONTA_HORAS}h foi expulso automaticamente pelo anti-raid (ID: {member.id}).",
            )
        except discord.Forbidden:
            logger.warning(
                "Sem permissão/hierarquia para expulsar possível conta de raid (guild=%s, member=%s).",
                guild_id, member.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Falha HTTP ao expulsar possível conta de raid (guild=%s, member=%s).",
                guild_id, member.id,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
