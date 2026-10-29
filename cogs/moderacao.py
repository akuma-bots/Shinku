from utils.apresentacao import criar_embed
import datetime
import logging
import discord
from discord import app_commands
from discord.ext import commands
from utils.punicoes import registrar_punicao, historico_punicoes


CANAL_REGRAS_ID = 1563995880833421508


class Moderacao(commands.Cog):
    """Comandos manuais de moderação."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log(self, interaction: discord.Interaction, texto: str):
        """Registra a ação sem transformar uma falha de log em falha do comando."""
        from utils.guild_config import get_config

        if interaction.guild is None:
            return

        try:
            config = await get_config(interaction.guild.id)
            log_id = config.get("log_channel_id") or 1545838386944938024
            if not log_id:
                return

            canal = interaction.guild.get_channel(int(log_id))
            if canal is None:
                canal = await interaction.guild.fetch_channel(int(log_id))

            if not callable(getattr(canal, "send", None)):
                logging.warning("Canal de logs %s não aceita mensagens.", log_id)
                return

            await canal.send(texto, allowed_mentions=discord.AllowedMentions.none())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            logging.exception("Não foi possível registrar a ação de moderação no canal de logs.")
        except Exception:
            logging.exception("Falha inesperada ao registrar ação de moderação.")

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

    async def _validar_alvo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
    ) -> bool:
        """Impede punições inválidas por autoalvo ou hierarquia do Discord."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado dentro do servidor.",
                ephemeral=True,
            )
            return False

        if membro.id == interaction.user.id:
            await interaction.response.send_message(
                "Você não pode aplicar uma punição em si mesmo.",
                ephemeral=True,
            )
            return False

        if membro.id == self.bot.user.id:
            await interaction.response.send_message(
                "Não é possível aplicar uma punição no próprio bot.",
                ephemeral=True,
            )
            return False

        if membro.id == guild.owner_id:
            await interaction.response.send_message(
                "O proprietário do servidor não pode ser punido por este comando.",
                ephemeral=True,
            )
            return False

        autor = interaction.user
        if (
            isinstance(autor, discord.Member)
            and autor.id != guild.owner_id
            and membro.top_role >= autor.top_role
        ):
            await interaction.response.send_message(
                "Você não pode punir alguém com cargo igual ou superior ao seu.",
                ephemeral=True,
            )
            return False

        bot_membro = guild.me
        if bot_membro is None or membro.top_role >= bot_membro.top_role:
            await interaction.response.send_message(
                "Não consigo punir este membro: meu cargo precisa estar acima do cargo mais alto dele.",
                ephemeral=True,
            )
            return False

        return True

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
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str = "Não especificado"
    ):
        if not await self._validar_alvo(interaction, membro):
            return

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
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: str = "Não especificado"
    ):
        if not await self._validar_alvo(interaction, membro):
            return

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
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        minutos: app_commands.Range[int, 1, 40320],
        motivo: str = "Não especificado"
    ):
        if not await self._validar_alvo(interaction, membro):
            return

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
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: discord.Interaction,
        membro: discord.Member
    ):
        if not await self._validar_alvo(interaction, membro):
            return

        await membro.timeout(None)

        await interaction.response.send_message(
            f"🔊 {membro.mention} não está mais silenciado.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._log(
            interaction,
            f"🔊 **/unmute** — {membro.mention} teve o silenciamento removido por "
            f"{interaction.user.mention}.",
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
        if not await self._validar_alvo(interaction, membro):
            return

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
        quantidade="Quantidade de mensagens a apagar (1-1000)"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    @app_commands.checks.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, 1, 1000]
    ):
        """Apaga até 1.000 mensagens usando a rotina otimizada do discord.py."""
        canal = interaction.channel
        if not isinstance(canal, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Este comando só pode ser usado em canais de texto ou tópicos.",
                ephemeral=True
            )
            return

        # Reconhece a interação antes da operação de rede, evitando timeout.
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # purge agrupa mensagens em lotes e trata mensagens antigas
            # (com mais de 14 dias) individualmente, conforme a API do Discord.
            apagadas = await canal.purge(
                limit=quantidade,
                bulk=True,
                oldest_first=False,
                reason=f"/clear executado por {interaction.user} ({interaction.user.id})"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Não consegui apagar as mensagens. Verifique as permissões do bot "
                "para gerenciar mensagens e ler o histórico deste canal.",
                ephemeral=True
            )
            return
        except discord.HTTPException:
            logging.exception("Falha da API do Discord durante /clear.")
            await interaction.followup.send(
                "O Discord não concluiu a limpeza. Algumas mensagens podem ter sido "
                "apagadas antes do erro; tente novamente com uma quantidade menor.",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"🧹 Limpeza concluída: **{len(apagadas)}** de até **{quantidade}** "
            f"mensagens apagadas em {canal.mention}.",
            ephemeral=True
        )

        await self._log(
            interaction,
            f"🧹 **/clear** — {interaction.user.mention} apagou "
            f"**{len(apagadas)}** mensagens em {canal.mention} "
            f"(limite solicitado: {quantidade})."
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

            embed = criar_embed(
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

        embed = criar_embed(
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
        if isinstance(error, app_commands.MissingPermissions):
            mensagem = "Você não tem permissão para usar esse comando."
        elif isinstance(error, app_commands.BotMissingPermissions):
            permissoes = ", ".join(error.missing_permissions)
            mensagem = (
                "Não consigo executar esta ação porque faltam permissões no bot: "
                f"**{permissoes}**. Peça à administração para revisar as permissões."
            )
        else:
            raise error

        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(
        Moderacao(bot)
    )