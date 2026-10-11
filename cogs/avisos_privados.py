import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.avisos_privados import definir_inscricao, obter_estado_guild
from utils.storage import carregar, salvar

ARQUIVO = "avisos_privados.json"
LIMITE_POR_ENVIO = 500
INTERVALO_ENVIO = 1.0

TIPOS_AVISO = [
    app_commands.Choice(name="Novidades da NÊMESIS", value="Novidades"),
    app_commands.Choice(name="Sistemas novos", value="Sistemas novos"),
    app_commands.Choice(name="Eventos", value="Eventos"),
    app_commands.Choice(name="Manutenção", value="Manutenção"),
    app_commands.Choice(name="Aviso importante", value="Aviso importante"),
]

logger = logging.getLogger(__name__)


class AvisosPrivados(commands.Cog):
    """Avisos por DM para membros que optaram explicitamente por receber."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _carregar_estado(self):
        dados = await carregar(ARQUIVO, {"guilds": {}})
        if not isinstance(dados, dict):
            dados = {"guilds": {}}
        return dados

    @app_commands.command(
        name="avisos-privados",
        description="Ativa ou desativa o recebimento de novidades da NÊMESIS por mensagem privada.",
    )
    @app_commands.describe(receber="Escolha se deseja receber avisos privados.")
    @app_commands.choices(receber=[
        app_commands.Choice(name="Ativar", value="ativar"),
        app_commands.Choice(name="Desativar", value="desativar"),
    ])
    async def avisos_privados(
        self,
        interaction: discord.Interaction,
        receber: app_commands.Choice[str],
    ):
        if interaction.guild_id is None or interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.", ephemeral=True
            )
            return

        try:
            dados = await self._carregar_estado()
            ativar = receber.value == "ativar"
            dados, estado = definir_inscricao(
                dados, interaction.guild_id, interaction.user.id, ativar
            )
            await salvar(ARQUIVO, dados)
        except Exception:
            logger.exception(
                "Falha ao atualizar inscrição de avisos privados (guild=%s, user=%s)",
                interaction.guild_id, interaction.user.id,
            )
            await interaction.response.send_message(
                "Não consegui salvar sua preferência agora. Tente novamente mais tarde.",
                ephemeral=True,
            )
            return

        if receber.value == "ativar":
            texto = (
                "Você ativou os avisos privados da NÊMESIS. "
                "Você receberá comunicados sobre novidades, sistemas, eventos e avisos importantes. "
                "Para parar, use `/avisos-privados` e escolha **Desativar**."
            )
        else:
            texto = "Avisos privados desativados. Você não receberá novos comunicados por DM."

        await interaction.response.send_message(texto, ephemeral=True)

    @app_commands.command(
        name="avisos-enviar",
        description="Envia um comunicado por DM somente a membros inscritos nos avisos privados.",
    )
    @app_commands.describe(
        tipo="Categoria do comunicado",
        titulo="Título mostrado na mensagem",
        mensagem="Texto do comunicado (máximo de 3000 caracteres)",
    )
    @app_commands.choices(tipo=TIPOS_AVISO)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def avisos_enviar(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        titulo: str,
        mensagem: str,
    ):
        guild = interaction.guild
        if guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.", ephemeral=True
            )
            return

        titulo = titulo.strip()
        mensagem = mensagem.strip()
        if not titulo or len(titulo) > 200:
            await interaction.response.send_message(
                "O título precisa ter entre 1 e 200 caracteres.", ephemeral=True
            )
            return
        if not mensagem or len(mensagem) > 3000:
            await interaction.response.send_message(
                "A mensagem precisa ter entre 1 e 3000 caracteres.", ephemeral=True
            )
            return

        try:
            dados = await self._carregar_estado()
            dados, estado = obter_estado_guild(dados, guild.id)
            inscritos = list(estado["inscritos"])
        except Exception:
            logger.exception("Falha ao carregar inscritos dos avisos privados.")
            await interaction.response.send_message(
                "Não foi possível carregar a lista de inscritos.", ephemeral=True
            )
            return

        if not inscritos:
            await interaction.response.send_message(
                "Ainda não há membros inscritos nos avisos privados.", ephemeral=True
            )
            return

        if len(inscritos) > LIMITE_POR_ENVIO:
            await interaction.response.send_message(
                f"Este comunicado alcançaria {len(inscritos)} inscritos. "
                f"O limite por envio é {LIMITE_POR_ENVIO}; nenhum DM foi enviado. "
                "Divida o comunicado em lotes ou reduza a lista de inscritos.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — {tipo.value} · {titulo}",
            description=mensagem,
            color=0xB3132B,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="NÊMESIS • Avisos privados | Para deixar de receber, use /avisos-privados")

        await interaction.response.defer(ephemeral=True, thinking=True)
        enviados = 0
        falhas = 0
        ausentes = 0

        for indice, user_id in enumerate(inscritos):
            membro = guild.get_member(int(user_id))
            if membro is None:
                try:
                    membro = await guild.fetch_member(int(user_id))
                except discord.NotFound:
                    ausentes += 1
                    continue
                except discord.HTTPException as erro:
                    falhas += 1
                    logger.warning(
                        "Falha ao localizar inscrito (guild=%s, user=%s, status=%s)",
                        guild.id, user_id, getattr(erro, "status", "desconhecido"),
                    )
                    continue

            try:
                await membro.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                enviados += 1
            except discord.Forbidden:
                falhas += 1
            except discord.HTTPException as erro:
                falhas += 1
                logger.warning(
                    "Falha ao enviar aviso privado (guild=%s, user=%s, status=%s)",
                    guild.id, membro.id, getattr(erro, "status", "desconhecido"),
                )

            if indice < len(inscritos) - 1:
                await asyncio.sleep(INTERVALO_ENVIO)

        estado["ultimo_envio"] = {
            "tipo": tipo.value,
            "titulo": titulo,
            "enviado_por": str(interaction.user.id),
            "criado_em": datetime.now(timezone.utc).isoformat(),
            "inscritos_no_inicio": len(inscritos),
            "enviados": enviados,
            "falhas": falhas,
            "ausentes": ausentes,
        }
        dados["guilds"][str(guild.id)] = estado
        try:
            await salvar(ARQUIVO, dados)
        except Exception:
            logger.exception("Falha ao salvar relatório do aviso privado.")

        await interaction.followup.send(
            f"**Comunicado concluído: {titulo}**\n"
            f"• Enviados: **{enviados}**\n"
            f"• Falhas (DM fechada ou erro do Discord): **{falhas}**\n"
            f"• Inscritos não encontrados no servidor: **{ausentes}**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AvisosPrivados(bot))
