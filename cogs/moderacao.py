import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.punicoes import registrar_punicao, historico_punicoes


CANAL_REGRAS_ID = 1545831172796583987


class Moderacao(commands.Cog):
    """Comandos manuais de moderação."""

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

    async def _carregar_regras_oficiais(self, guild: discord.Guild):
        """
        Carrega as regras diretamente do canal oficial.
        Não utiliza rules.json.
        """

        canal = guild.get_channel(CANAL_REGRAS_ID)

        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_REGRAS_ID)
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):
                return None

        if not isinstance(canal, discord.TextChannel):
            return None

        mensagens = []

        try:
            async for mensagem in canal.history(
                limit=200,
                oldest_first=True
            ):
                conteudo = mensagem.content.strip()

                if conteudo:
                    mensagens.append(conteudo)

                # Também lê regras que estejam dentro de embeds.
                for embed in mensagem.embeds:

                    if embed.title:
                        mensagens.append(
                            f"**{embed.title}**"
                        )

                    if embed.description:
                        mensagens.append(
                            embed.description
                        )

                    for campo in embed.fields:
                        mensagens.append(
                            f"**{campo.name}**\n{campo.value}"
                        )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            return None

        if not mensagens:
            return None

        return "\n\n".join(mensagens)

    @app_commands.command(
        name="ban",
        description="Bane um membro do servidor."
    )
    @app_commands.describe(
        membro="Membro a ser banido",
        motivo="Motivo do banimento"
    )
    @app_commands.checks.has_permissions(
        ban_members=True
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str = "Não especificado"
    ):
        await membro.ban(
            reason=motivo,
            delete_message_days=0
        )

        await registrar_punicao(
            interaction.guild.id,
            membro.id,
            "ban",
            motivo,
            interaction.user.id
        )

        await interaction.response.send_message(
            f"🔨 {membro.mention} foi banido. "
            f"Motivo: {motivo}"
        )

        await self._log(
            interaction,
            f"🔨 {membro.mention} banido por "
            f"{interaction.user.mention} — {motivo}"
        )

    @app_commands.command(
        name="kick",
        description="Expulsa um membro do servidor."
    )
    @app_commands.describe(
        membro="Membro a ser expulso",
        motivo="Motivo da expulsão"
    )
    @app_commands.checks.has_permissions(
        kick_members=True
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str = "Não especificado"
    ):
        await membro.kick(reason=motivo)

        await registrar_punicao(
            interaction.guild.id,
            membro.id,
            "kick",
            motivo,
            interaction.user.id
        )

        await interaction.response.send_message(
            f"👢 {membro.mention} foi expulso. "
            f"Motivo: {motivo}"
        )

        await self._log(
            interaction,
            f"👢 {membro.mention} expulso por "
            f"{interaction.user.mention} — {motivo}"
        )

    @app_commands.command(
        name="mute",
        description="Silencia um membro por um tempo determinado."
    )
    @app_commands.describe(
        membro="Membro a silenciar",
        minutos="Duração em minutos",
        motivo="Motivo"
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        minutos: int,
        motivo: str = "Não especificado"
    ):
        ate = (
            discord.utils.utcnow()
            + datetime.timedelta(minutes=minutos)
        )

        await membro.timeout(
            ate,
            reason=motivo
        )

        await registrar_punicao(
            interaction.guild.id,
            membro.id,
            "mute",
            f"{motivo} ({minutos} min)",
            interaction.user.id
        )

        await interaction.response.send_message(
            f"🔇 {membro.mention} foi silenciado "
            f"por {minutos} min. Motivo: {motivo}"
        )

        await self._log(
            interaction,
            f"🔇 {membro.mention} silenciado por "
            f"{interaction.user.mention} "
            f"({minutos} min) — {motivo}"
        )

    @app_commands.command(
        name="unmute",
        description="Remove o silenciamento de um membro."
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def unmute(
        self,
        interaction: discord.Interaction,
        membro: discord.Member
    ):
        await membro.timeout(None)

        await interaction.response.send_message(
            f"🔊 {membro.mention} não está mais silenciado."
        )

    @app_commands.command(
        name="warn",
        description="Registra um aviso manual para um membro."
    )
    @app_commands.describe(
        membro="Membro a avisar",
        motivo="Motivo do aviso"
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str
    ):
        try:
            await membro.send(
                f"⚠️ Você recebeu um aviso em "
                f"**{interaction.guild.name}**: {motivo}"
            )
        except discord.Forbidden:
            pass

        await registrar_punicao(
            interaction.guild.id,
            membro.id,
            "warn",
            motivo,
            interaction.user.id
        )

        await interaction.response.send_message(
            f"⚠️ {membro.mention} foi avisado. "
            f"Motivo: {motivo}"
        )

        await self._log(
            interaction,
            f"⚠️ {membro.mention} avisado manualmente por "
            f"{interaction.user.mention} — {motivo}"
        )

    @app_commands.command(
        name="clear",
        description="Apaga uma quantidade de mensagens do canal."
    )
    @app_commands.describe(
        quantidade="Quantidade de mensagens a apagar (1-100)"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, 1, 100]
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        apagadas = await interaction.channel.purge(
            limit=quantidade
        )

        await interaction.followup.send(
            f"🧹 {len(apagadas)} mensagens apagadas.",
            ephemeral=True
        )

    @app_commands.command(
        name="regras",
        description="Mostra as regras oficiais do servidor."
    )
    async def regras(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer()

        regras = await self._carregar_regras_oficiais(
            interaction.guild
        )

        if not regras:
            await interaction.followup.send(
                "❌ Não foi possível carregar as regras.\n\n"
                f"Verifique se o canal <#{CANAL_REGRAS_ID}> "
                "existe e se o bot possui permissão para "
                "visualizar o canal e o histórico de mensagens."
            )
            return

        # Limite seguro para a descrição de uma embed.
        limite = 3900

        partes = []

        while len(regras) > limite:
            corte = regras.rfind(
                "\n",
                0,
                limite
            )

            if corte <= 0:
                corte = regras.rfind(
                    " ",
                    0,
                    limite
                )

            if corte <= 0:
                corte = limite

            partes.append(
                regras[:corte].strip()
            )

            regras = regras[corte:].strip()

        if regras:
            partes.append(regras)

        embeds = []

        for indice, parte in enumerate(
            partes,
            start=1
        ):
            titulo = "📜 Regras do Servidor"

            if len(partes) > 1:
                titulo += (
                    f" — Parte {indice}/{len(partes)}"
                )

            embed = discord.Embed(
                title=titulo,
                description=parte,
                color=0x5865F2
            )

            embed.set_footer(
                text="Fonte oficial: canal de regras"
            )

            embeds.append(embed)

        await interaction.followup.send(
            embeds=embeds
        )

    @app_commands.command(
        name="avisos",
        description="Mostra os avisos automáticos registrados de um membro."
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def avisos(
        self,
        interaction: discord.Interaction,
        membro: discord.Member
    ):
        from utils.storage import carregar

        dados = await carregar(
            "avisos.json",
            {}
        )

        registros = dados.get(
            str(interaction.guild.id),
            {}
        ).get(
            str(membro.id),
            {}
        )

        if not registros:
            await interaction.response.send_message(
                f"{membro.mention} não tem avisos registrados.",
                ephemeral=True
            )
            return

        texto = "\n".join(
            f"• {regra_id}: {qtd}"
            for regra_id, qtd in registros.items()
        )

        await interaction.response.send_message(
            f"Avisos de {membro.mention}:\n{texto}",
            ephemeral=True
        )

    @app_commands.command(
        name="punicoes-historico",
        description="Mostra o histórico de punições de um membro ou do servidor."
    )
    @app_commands.describe(
        membro="Opcional: filtra apenas esse membro"
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def punicoes_historico(
        self,
        interaction: discord.Interaction,
        membro: discord.Member = None
    ):
        registros = await historico_punicoes(
            interaction.guild.id,
            membro.id if membro else None
        )

        if not registros:
            await interaction.response.send_message(
                "Nenhuma punição registrada.",
                ephemeral=True
            )
            return

        emojis = {
            "ban": "🔨",
            "ban_temp": "⏳",
            "kick": "👢",
            "mute": "🔇",
            "warn": "⚠️",
            "aviso_automatico": "🤖"
        }

        linhas = []

        for p in registros:
            quem = (
                f"<@{p['aplicado_por_id']}>"
                if p["aplicado_por_id"]
                else "automod"
            )

            linhas.append(
                f"{emojis.get(p['tipo'], '•')} "
                f"<@{p['membro_id']}> — "
                f"**{p['tipo']}** por {quem}: "
                f"{p['motivo']}"
            )

        titulo = "📋 Histórico de punições"

        if membro:
            titulo += (
                f" — {membro.display_name}"
            )

        embed = discord.Embed(
            title=titulo,
            description="\n".join(linhas),
            color=0xED4245
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(
            error,
            app_commands.MissingPermissions
        ):
            mensagem = (
                "Você não tem permissão "
                "para usar esse comando."
            )

            if interaction.response.is_done():
                await interaction.followup.send(
                    mensagem,
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    mensagem,
                    ephemeral=True
                )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(
        Moderacao(bot)
    )