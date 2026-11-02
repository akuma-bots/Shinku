import logging
import time

import discord
from discord.ext import commands

from utils.guild_config import get_config, membro_pode_promover_rebaixar_banir


logger = logging.getLogger(__name__)

JANELA_SEGUNDOS = 10
LIMITE_ENTRADAS = 6
IDADE_MINIMA_CONTA_HORAS = 24


class AntiRaid(commands.Cog):
    """Detecta picos de entrada e sinaliza contas recentes para revisão humana."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._entradas_por_guild = {}
        self._raid_ativo = {}

    @staticmethod
    def _alvo_elegivel(member: discord.Member) -> bool:
        """Ignora bots e membros com privilégios administrativos ao avaliar alertas."""
        if (
            member.bot
            or member.id == member.guild.owner_id
            or membro_pode_promover_rebaixar_banir(member)
        ):
            return False
        return True

    async def _avisar(self, guild: discord.Guild, texto: str, mencionar_suporte: bool = False):
        from utils.registro_global import registrar
        config = await get_config(guild.id) if mencionar_suporte else {}
        cargo_id = config.get("support_role_id")
        cargo = guild.get_role(int(cargo_id)) if cargo_id else None
        await registrar(
            guild,
            "seguranca",
            "ALERTA DE SEGURANÇA • ANTI-RAID",
            texto.replace("🚨 **Possível raid detectado!** ", "")
                 .replace("🛡️ **Revisão recomendada:** ", ""),
            cor=0xED4245,
            content=cargo.mention if cargo and mencionar_suporte else None,
            allowed_mentions=(
                discord.AllowedMentions(roles=True, users=False, everyone=False)
                if cargo and mencionar_suporte else discord.AllowedMentions.none()
            ),
        )

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
                "para revisão da equipe; nenhuma punição será aplicada automaticamente.",
                mencionar_suporte=True,
            )

        if not self._raid_ativo.get(guild_id) or not self._alvo_elegivel(member):
            return

        idade_conta = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
        if idade_conta >= IDADE_MINIMA_CONTA_HORAS:
            return

        await self._avisar(
            member.guild,
            f"🛡️ **Revisão recomendada:** <@{member.id}> (ID: `{member.id}`) entrou durante um pico suspeito e a conta tem menos de {IDADE_MINIMA_CONTA_HORAS}h. Nenhuma punição automática foi aplicada; a equipe deve verificar o contexto.",
            mencionar_suporte=True,
        )
        logger.warning(
            "Conta recente sinalizada para revisão manual (guild=%s, member=%s, idade_horas=%.2f).",
            guild_id, member.id, idade_conta,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
