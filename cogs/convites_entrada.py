import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
CANAL_CONVITES_ID = 1563995880623841332
CANAL_ENTRADAS_ID = 1563995880623841331
COR_NEMESIS = 0xB3132B


def _embed_entrada(member: discord.Member) -> discord.Embed:
    nome = discord.utils.escape_markdown(member.display_name)
    embed = discord.Embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOVA PRESENÇA ・✦",
        description=(
            f"⟡・ **{nome}**, sua chegada marca o início de uma nova jornada.\n"
            "Você agora faz parte de uma organização construída sobre competitividade, "
            "evolução, lealdade e respeito."
        ),
        color=COR_NEMESIS,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="⟡・ CONHEÇA A NÊMESIS",
        value=(
            "Uma comunidade focada em jogos de luta, desafios, desenvolvimento dos membros "
            "e atividade coletiva. Aqui, sua participação e sua evolução fazem diferença."
        ),
        inline=False,
    )
    embed.add_field(
        name="Ⅰ  ━ PRIMEIROS PASSOS",
        value=(
            "➜ **Leia as regras oficiais** e conheça as orientações da organização.\n"
            "➜ **Confira os anúncios** para não perder comunicados, eventos e atualizações.\n"
            "➜ **Explore os canais** e identifique as áreas de conversa, jogos e suporte.\n"
            "➜ Use `/tutorial` para conhecer os sistemas e `/help` para consultar os comandos."
        ),
        inline=False,
    )
    embed.add_field(
        name="Ⅱ  ━ EVOLUA NA ORGANIZAÇÃO",
        value=(
            "⚔️ **Missões e desafios:** participe das atividades disponíveis.\n"
            "✦ **XP e progressão:** mantenha-se ativo para evoluir pelos cargos competitivos.\n"
            "◈ **Contribuição (P.C.):** confira as atividades que concedem pontos.\n"
            "⟡ **Equipe e atendimento:** se tiver dúvidas, procure os canais oficiais de suporte."
        ),
        inline=False,
    )
    embed.add_field(
        name="Ⅲ  ━ NOSSO CÓDIGO",
        value=(
            "Respeite os membros, siga as regras, evite conflitos desnecessários e mantenha "
            "a competitividade saudável. A equipe poderá orientar você sempre que necessário."
        ),
        inline=False,
    )
    embed.add_field(
        name="⟡・ SUA JORNADA COMEÇA AGORA",
        value=(
            "Apresente-se à comunidade, acompanhe as novidades e descubra onde sua habilidade "
            "pode chegar. **Bem-vindo à NÊMESIS.**"
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"NÊMESIS • Guia de entrada • Membro #{member.guild.member_count or 0}"
    )
    return embed


def _embed_convite(
    member: discord.Member,
    inviter: discord.abc.User | None,
    invite: discord.Invite | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — REGISTRO DE RECRUTAMENTO ・✦",
        description=(
            f"⟡・ {member.mention} acaba de entrar na NÊMESIS.\n"
            "Uma nova presença foi registrada no quadro de recrutamento."
        ),
        color=COR_NEMESIS,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="NOVO MEMBRO", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(
        name="CONVIDADO POR",
        value=f"{inviter.mention}\n`{inviter.id}`" if inviter else "Convite não identificado",
        inline=True,
    )
    if invite:
        embed.add_field(name="CÓDIGO UTILIZADO", value=f"`{invite.code}`", inline=True)
        embed.add_field(name="UTILIZAÇÕES DO CONVITE", value=str(invite.uses or 0), inline=True)
        embed.add_field(
            name="LIMITE",
            value="Ilimitado" if invite.max_uses == 0 else str(invite.max_uses),
            inline=True,
        )
    embed.add_field(
        name="CONTA CRIADA",
        value=discord.utils.format_dt(member.created_at, style="R"),
        inline=True,
    )
    embed.add_field(
        name="TOTAL DE MEMBROS",
        value=str(member.guild.member_count or "Indisponível"),
        inline=True,
    )
    embed.set_footer(text="NÊMESIS • Central de convites • Registro automático")
    return embed


class ConvitesEEntrada(commands.Cog):
    """Registra convites utilizados e publica um guia de entrada no servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._convites: dict[int, dict[str, tuple[int, int | None]]] = {}

    async def _buscar_convites(self, guild: discord.Guild) -> list[discord.Invite] | None:
        try:
            return await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Não foi possível consultar convites da guild=%s. Verifique a permissão Gerenciar Servidor.",
                guild.id,
            )
            return None

    async def _atualizar_cache(self, guild: discord.Guild) -> None:
        convites = await self._buscar_convites(guild)
        if convites is None:
            return
        self._convites[guild.id] = {
            convite.code: (convite.uses or 0, convite.inviter.id if convite.inviter else None)
            for convite in convites
        }

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_ID)
        if guild:
            await self._atualizar_cache(guild)
            logger.info("Cache de convites preparado (guild=%s).", guild.id)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild and invite.guild.id == GUILD_ID:
            await self._atualizar_cache(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild and invite.guild.id == GUILD_ID:
            await self._atualizar_cache(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != GUILD_ID or member.bot:
            return

        guild = member.guild
        anteriores = self._convites.get(guild.id, {})
        atuais_lista = await self._buscar_convites(guild)
        convite_usado = None
        inviter = None

        if atuais_lista is not None:
            atuais = {
                convite.code: (convite.uses or 0, convite.inviter.id if convite.inviter else None)
                for convite in atuais_lista
            }
            for convite in atuais_lista:
                usos_anteriores = anteriores.get(convite.code, (0, None))[0]
                if (convite.uses or 0) > usos_anteriores:
                    convite_usado = convite
                    inviter = convite.inviter
                    break
            self._convites[guild.id] = atuais

        try:
            canal_entrada = guild.get_channel(CANAL_ENTRADAS_ID) or await self.bot.fetch_channel(CANAL_ENTRADAS_ID)
            await canal_entrada.send(
                embed=_embed_entrada(member),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            logger.exception("Não foi possível publicar o guia de entrada (canal=%s).", CANAL_ENTRADAS_ID)

        try:
            canal_convites = guild.get_channel(CANAL_CONVITES_ID) or await self.bot.fetch_channel(CANAL_CONVITES_ID)
            await canal_convites.send(
                embed=_embed_convite(member, inviter, convite_usado),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            logger.exception("Não foi possível publicar o registro de convite (canal=%s).", CANAL_CONVITES_ID)

    @app_commands.command(name="convites", description="Consultar o total de utilizações dos convites da NÊMESIS.")
    @app_commands.guild_only()
    async def consultar_convites(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ):
        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message(
                "Este sistema está disponível apenas no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        alvo = membro or interaction.user
        convites = await self._buscar_convites(interaction.guild)
        if convites is None:
            await interaction.response.send_message(
                "Não consegui consultar os convites. A equipe precisa verificar se o bot tem a permissão **Gerenciar Servidor**.",
                ephemeral=True,
            )
            return

        criados = [
            convite for convite in convites
            if convite.inviter and convite.inviter.id == alvo.id
        ]
        total_usos = sum(convite.uses or 0 for convite in criados)
        embed = discord.Embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — PAINEL DE CONVITES ・✦",
            description=f"⟡・ Estatísticas de recrutamento de {alvo.mention}.",
            color=COR_NEMESIS,
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="CONVITES CRIADOS ATIVOS", value=str(len(criados)), inline=True)
        embed.add_field(name="ENTRADAS REGISTRADAS", value=str(total_usos), inline=True)
        if criados:
            linhas = [
                f"• `{convite.code}` — **{convite.uses or 0}** utilização(ões)"
                for convite in sorted(criados, key=lambda item: item.uses or 0, reverse=True)[:10]
            ]
            embed.add_field(name="DETALHAMENTO", value="\n".join(linhas), inline=False)
        else:
            embed.add_field(
                name="DETALHAMENTO",
                value="Nenhum convite ativo criado por este membro foi encontrado.",
                inline=False,
            )
        embed.set_footer(text="NÊMESIS • Estatísticas baseadas nos convites ativos do Discord")
        await interaction.response.send_message(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ConvitesEEntrada(bot))
