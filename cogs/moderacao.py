from utils.apresentacao import criar_embed
import logging
import discord
from discord import app_commands
from discord.ext import commands
from utils.punicoes import historico_punicoes
from utils.guild_config import hierarquia_only, lideranca_only, membro_pode_gerenciar_membro


CANAL_REGRAS_ID = 1563995880833421508


class Moderacao(commands.Cog):
    """Ferramentas auxiliares, consulta de regras e histórico de moderação."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log(self, interaction: discord.Interaction, texto: str):
        """Registra ações de moderação no tópico central, sem interromper comandos."""
        if interaction.guild is None:
            return
        from utils.registro_global import registrar
        await registrar(
            interaction.guild,
            "moderacao",
            "Ação de moderação",
            texto,
            cor=0xB3132B,
        )

    async def _carregar_regras_oficiais(self, guild: discord.Guild):
        """Recupera a embed oficial integral, sem reconstruí-la em várias mensagens."""
        canal = guild.get_channel(CANAL_REGRAS_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_REGRAS_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        if not isinstance(canal, discord.TextChannel):
            return None

        try:
            async for mensagem in canal.history(limit=200, oldest_first=False):
                for embed in mensagem.embeds:
                    rodape = embed.footer.text or ""
                    if (
                        embed.title == "𓂀 NÊMESIS — CÓDIGO DE CONDUTA"
                        and rodape.startswith("NÊMESIS • Código de Conduta oficial")
                        and len(embed.fields) == 11
                    ):
                        return embed.copy()
        except (discord.Forbidden, discord.HTTPException):
            logging.exception("Falha ao consultar a embed oficial do Código de Conduta.")
            return None
        return None

    @app_commands.command(
        name="clear",
        description="Apaga uma quantidade de mensagens do canal."
    )
    @app_commands.describe(
        quantidade="Quantidade de mensagens a apagar (1-1000)"
    )
    @lideranca_only()
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
        name="banir",
        description="Bane um membro abaixo da sua posição hierárquica."
    )
    @app_commands.describe(
        membro="Membro que será banido",
        motivo="Motivo do banimento para o registro de auditoria",
    )
    @hierarquia_only()
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def banir(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: app_commands.Range[str, 5, 500],
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if membro.id == interaction.guild.owner_id or membro.bot:
            await interaction.response.send_message("Este membro não pode ser banido por este comando.", ephemeral=True)
            return
        if not membro_pode_gerenciar_membro(interaction.user, membro):
            await interaction.response.send_message(
                "A ação foi bloqueada: o alvo possui cargo igual ou superior ao seu, ou está fora da hierarquia autorizada.",
                ephemeral=True,
            )
            return
        motivo_seguro = discord.utils.escape_markdown(motivo.strip())[:500]
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await interaction.guild.ban(
                membro,
                reason=f"Banimento hierárquico por {interaction.user} ({interaction.user.id}): {motivo_seguro}",
                delete_message_seconds=0,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "O Discord recusou o banimento. Verifique a permissão Banir membros e a hierarquia do cargo do bot.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logging.exception("Falha ao banir membro por comando hierárquico.")
            await interaction.followup.send(
                "O Discord não concluiu o banimento. Confira o histórico de auditoria antes de repetir.",
                ephemeral=True,
            )
            return
        await self._log(
            interaction,
            f"🔨 **/banir** — {interaction.user.mention} baniu {membro.mention}. Motivo: {motivo_seguro}",
        )
        await interaction.followup.send(
            f"Banimento aplicado a **{discord.utils.escape_markdown(membro.display_name)}**. O histórico de mensagens não foi apagado.",
            ephemeral=True,
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

        embed = await self._carregar_regras_oficiais(interaction.guild)

        if embed is None:
            await interaction.followup.send(
                "❌ Não foi possível carregar a embed oficial das regras. "
                f"Verifique o canal <#{CANAL_REGRAS_ID}> e as permissões de leitura do bot."
            )
            return

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="avisos",
        description="Mostra os avisos automáticos registrados de um membro."
    )
    @lideranca_only()
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
    @lideranca_only()
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