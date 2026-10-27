import asyncio
import logging
from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
ARQUIVO_CONVITES = "convites_nemesis.json"


class ConvitesNemesis(commands.Cog):
    """Rastreia o convidador original e conta apenas membros atualmente presentes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._convites: dict[int, dict[str, tuple[int, int | None]]] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._inicializados: set[int] = set()

    async def _buscar_convites(self, guild: discord.Guild):
        try:
            convites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível ler convites da guild=%s. Verifique Gerenciar servidor.", guild.id)
            return None
        return {
            invite.code: (invite.uses or 0, invite.inviter.id if invite.inviter else None)
            for invite in convites
        }

    async def _carregar_dados(self):
        dados = await carregar(ARQUIVO_CONVITES, {})
        if not isinstance(dados, dict):
            dados = {}
        servidor = dados.setdefault(str(GUILD_NEMESIS_ID), {})
        servidor.setdefault("_historico", {})
        return dados, servidor

    async def _salvar_dados(self, dados):
        await salvar(ARQUIVO_CONVITES, dados)

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None or guild.id in self._inicializados:
            return
        cache = await self._buscar_convites(guild)
        if cache is not None:
            self._convites[guild.id] = cache
            self._inicializados.add(guild.id)
            logger.info("Cache de convites inicializado (guild=%s, convites=%s).", guild.id, len(cache))

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        async with self._locks[invite.guild.id]:
            self._convites.setdefault(invite.guild.id, {})[invite.code] = (
                invite.uses or 0, invite.inviter.id if invite.inviter else None
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        async with self._locks[invite.guild.id]:
            self._convites.setdefault(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if guild.id != GUILD_NEMESIS_ID or member.bot:
            return
        async with self._locks[guild.id]:
            dados, servidor = await self._carregar_dados()
            historico = servidor.setdefault("_historico", {})
            member_key = str(member.id)

            # Retorno de membro conhecido: reativa o vínculo original sem duplicar nem reatribuir.
            convidador_salvo = historico.get(member_key)
            if convidador_salvo:
                registro = servidor.setdefault(str(convidador_salvo), {"total": 0, "membros": []})
                ativos = set(map(str, registro.setdefault("membros", [])))
                ativos.add(member_key)
                registro["membros"] = sorted(ativos)
                registro["total"] = len(ativos)
                await self._salvar_dados(dados)
                logger.info("Membro retornou; vínculo original restaurado (guild=%s, member=%s, inviter=%s).",
                            guild.id, member.id, convidador_salvo)
                return

            anterior = self._convites.get(guild.id)
            atual = await self._buscar_convites(guild)
            if atual is None:
                return
            self._convites[guild.id] = atual
            if anterior is None:
                return

            usados = [
                (code, invite_data)
                for code, invite_data in atual.items()
                if code in anterior and invite_data[0] > anterior[code][0]
            ]
            if len(usados) != 1:
                logger.info("Convite não identificado com segurança (guild=%s, member=%s, candidatos=%s).",
                            guild.id, member.id, len(usados))
                return

            code, (_, inviter_id) = usados[0]
            if not inviter_id or inviter_id == member.id:
                return

            historico[member_key] = str(inviter_id)
            registro = servidor.setdefault(str(inviter_id), {"total": 0, "membros": []})
            ativos = set(map(str, registro.setdefault("membros", [])))
            ativos.add(member_key)
            registro["membros"] = sorted(ativos)
            registro["total"] = len(ativos)
            registro["ultimo_membro"] = member.id
            registro["ultimo_codigo"] = code
            await self._salvar_dados(dados)
            logger.info("Convite atribuído (guild=%s, inviter=%s, member=%s, code=%s).",
                        guild.id, inviter_id, member.id, code)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != GUILD_NEMESIS_ID or member.bot:
            return
        async with self._locks[member.guild.id]:
            dados, servidor = await self._carregar_dados()
            member_key = str(member.id)
            removido = False
            for user_id, registro in servidor.items():
                if user_id.startswith("_") or not isinstance(registro, dict):
                    continue
                ativos = set(map(str, registro.get("membros", [])))
                if member_key in ativos:
                    ativos.remove(member_key)
                    registro["membros"] = sorted(ativos)
                    registro["total"] = len(ativos)
                    removido = True
            # O histórico é preservado para que uma reentrada não conte como novo convite.
            if removido:
                await self._salvar_dados(dados)
                logger.info("Membro saiu; removido da contagem ativa (guild=%s, member=%s).",
                            member.guild.id, member.id)

    @app_commands.command(name="convites", description="Mostra quantos convidados seus continuam na NÊMESIS.")
    @app_commands.guild_only()
    async def meus_convites(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este comando só funciona na NÊMESIS.", ephemeral=True)
            return
        try:
            dados, servidor = await self._carregar_dados()
            registro = servidor.get(str(interaction.user.id), {})
            ativos = set(map(str, registro.get("membros", [])))
            embed = discord.Embed(
                title="✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — SEUS CONVITES・✦",
                description=f"Você tem **{len(ativos)}** membro(s) convidado(s) que continuam no servidor.",
                color=0xB51F32,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="Saídas são descontadas; reentradas não geram duplicatas.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Falha ao consultar convites do usuário=%s.", interaction.user.id)
            await interaction.response.send_message("Não consegui consultar seus convites agora. A equipe técnica foi avisada.", ephemeral=True)

    @app_commands.command(name="ranking-convites", description="Ranking de convidados que continuam na NÊMESIS.")
    @app_commands.guild_only()
    async def ranking_convites(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este comando só funciona na NÊMESIS.", ephemeral=True)
            return
        try:
            _, servidor = await self._carregar_dados()
            ranking = sorted(
                ((user_id, len(set(map(str, item.get("membros", [])))))
                 for user_id, item in servidor.items()
                 if not user_id.startswith("_") and isinstance(item, dict)),
                key=lambda item: item[1],
                reverse=True,
            )
            linhas = []
            for posicao, (user_id, total) in enumerate((item for item in ranking if item[1] > 0)[:10], start=1):
                linhas.append(f"**{posicao}.** <@{user_id}> — **{total}** membro(s) ativo(s)")
            embed = discord.Embed(
                title="✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — RANKING DE CONVITES・✦",
                description="\n".join(linhas) if linhas else "Ainda não há convidados ativos contabilizados.",
                color=0xB51F32,
            )
            embed.set_footer(text="Só contam membros presentes no servidor; sem duplicatas.")
            await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            logger.exception("Falha ao montar ranking de convites.")
            await interaction.response.send_message("Não consegui carregar o ranking agora. A equipe técnica foi avisada.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConvitesNemesis(bot))
