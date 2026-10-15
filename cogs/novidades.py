import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar, salvar


logger = logging.getLogger(__name__)
ARQUIVO_ESTADO = "novidades_automaticas.json"
CAMINHO_RELEASE = Path(__file__).resolve().parent.parent / "config" / "novidades.json"
CONCORRENCIA_ENVIO = 5
INTERVALO_ENVIO = 1.2  # Mantido apenas para a fila de releases automáticos.
TENTATIVAS_DM = 3


async def _enviar_dm_com_retry(membro: discord.abc.User, *, embed: discord.Embed) -> str:
    """Retorna enviada, permanente ou temporaria; repete falhas transitórias."""
    user_id = getattr(membro, "id", "desconhecido")
    for tentativa in range(1, TENTATIVAS_DM + 1):
        try:
            await membro.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return "enviada"
        except (discord.Forbidden, discord.NotFound):
            # Bloqueio de DM ou usuário inexistente não se resolve com retry.
            logger.info("DM indisponível permanentemente (user=%s).", user_id)
            return "permanente"
        except discord.HTTPException as erro:
            status = getattr(erro, "status", 0)
            codigo = getattr(erro, "code", 0)
            if status and 400 <= status < 500 and status != 429:
                logger.warning(
                    "DM rejeitada permanentemente (user=%s, status=%s, code=%s).",
                    user_id, status, codigo,
                )
                return "permanente"
            if tentativa >= TENTATIVAS_DM:
                logger.warning(
                    "DM falhou após %s tentativas (user=%s, status=%s, code=%s).",
                    tentativa, user_id, status, codigo, exc_info=True,
                )
                return "temporaria"
            espera = min(2 ** (tentativa - 1), 8)
            retry_after = getattr(erro, "retry_after", None)
            if isinstance(retry_after, (int, float)):
                espera = max(espera, min(float(retry_after), 30))
            logger.warning(
                "Falha HTTP transitória na DM (user=%s, tentativa=%s/%s); retry em %.1fs.",
                user_id, tentativa, TENTATIVAS_DM, espera,
            )
        except (asyncio.TimeoutError, OSError, discord.ConnectionClosed) as erro:
            if tentativa >= TENTATIVAS_DM:
                logger.warning(
                    "Falha de conexão ao enviar DM após %s tentativas (user=%s): %s",
                    tentativa, user_id, erro, exc_info=True,
                )
                return "temporaria"
            espera = min(2 ** (tentativa - 1), 8)
            logger.warning(
                "Conexão instável ao enviar DM (user=%s, tentativa=%s/%s); retry em %.1fs.",
                user_id, tentativa, TENTATIVAS_DM, espera,
            )
        except Exception:
            logger.exception("Erro inesperado ao enviar DM para %s.", user_id)
            return "temporaria"
        await asyncio.sleep(espera)
    return "temporaria"


class Novidades(commands.Cog):
    """Entrega uma vez cada release a todos os membros humanos do servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self._processando = False

    def _ler_release(self) -> dict | None:
        try:
            release = json.loads(CAMINHO_RELEASE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("Manifesto de novidades não encontrado: %s", CAMINHO_RELEASE)
            return None
        except (OSError, json.JSONDecodeError):
            logger.exception("Não foi possível ler o manifesto de novidades.")
            return None

        if not isinstance(release, dict):
            return None
        release_id = str(release.get("release_id", "")).strip()
        titulo = str(release.get("titulo", "")).strip()
        mensagem = str(release.get("mensagem", "")).strip()
        if not release_id or not titulo or not mensagem:
            logger.error("Manifesto de novidades incompleto; release_id, titulo e mensagem são obrigatórios.")
            return None
        return {
            "release_id": release_id[:100],
            "titulo": titulo[:200],
            "mensagem": mensagem[:3500],
            "tipo": str(release.get("tipo", "Sistemas novos"))[:100],
        }

    @app_commands.command(
        name="avisos-enviar",
        description="Envia um comunicado privado a todos os membros humanos da NÊMESIS.",
    )
    @app_commands.describe(
        tipo="Categoria do comunicado",
        titulo="Título mostrado na mensagem",
        mensagem="Texto do comunicado (máximo de 3000 caracteres)",
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Novidades da NÊMESIS", value="Novidades"),
        app_commands.Choice(name="Sistemas novos", value="Sistemas novos"),
        app_commands.Choice(name="Eventos", value="Eventos"),
        app_commands.Choice(name="Manutenção", value="Manutenção"),
        app_commands.Choice(name="Aviso importante", value="Aviso importante"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def avisos_enviar(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        titulo: str,
        mensagem: str,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        titulo = titulo.strip()
        mensagem = mensagem.strip()
        if not titulo or len(titulo) > 200:
            await interaction.response.send_message(
                "O título precisa ter entre 1 e 200 caracteres.",
                ephemeral=True,
            )
            return
        if not mensagem or len(mensagem) > 3000:
            await interaction.response.send_message(
                "A mensagem precisa ter entre 1 e 3000 caracteres.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
        except discord.HTTPException:
            logger.exception("Não foi possível obter a lista completa de membros para aviso privado.")
            await interaction.followup.send(
                "Não consegui carregar todos os membros. Nenhum comunicado foi enviado; tente novamente.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            description=(
                "╭────────────── ◈ ──────────────╮\n"
                "**𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  COMUNICADO OFICIAL**\n"
                "╰────────────── ◈ ──────────────╯\n\n"
                f"**{titulo}**\n"
                f"{mensagem}\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Este comunicado oficial é enviado a todos os membros humanos da NÊMESIS."
            ),
            color=0xB3132B,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="◈ CATEGORIA", value=f"**{tipo.value}**", inline=True)
        embed.add_field(name="◈ ENVIADO POR", value=interaction.user.mention, inline=True)
        embed.set_footer(text="NÊMESIS • Comunicados oficiais")

        async def processar_envio_em_segundo_plano():
            enviados = 0
            falhas = 0
            permanentes = 0
            semaforo = asyncio.Semaphore(CONCORRENCIA_ENVIO)

            async def enviar_para_membro(membro: discord.Member) -> tuple[int, str]:
                async with semaforo:
                    resultado = await _enviar_dm_com_retry(membro, embed=embed)
                    return membro.id, resultado

            tarefas = [asyncio.create_task(enviar_para_membro(membro)) for membro in membros]
            total = len(tarefas)
            for concluido, tarefa in enumerate(asyncio.as_completed(tarefas), start=1):
                user_id, resultado = await tarefa
                if resultado == "enviada":
                    enviados += 1
                else:
                    falhas += 1
                    if resultado == "permanente":
                        permanentes += 1
                    logger.info(
                        "Comunicado manual não entregue (guild=%s, user=%s, resultado=%s).",
                        guild.id, user_id, resultado,
                    )

                if concluido % 25 == 0 and concluido < total:
                    try:
                        await interaction.edit_original_response(
                            content=(
                                f"**Enviando comunicado: {titulo}**\n"
                                f"Progresso: **{concluido}/{total}** membros processados.\n"
                                f"DMs enviadas: **{enviados}** · Falhas: **{falhas}**"
                            )
                        )
                    except discord.HTTPException:
                        logger.debug("Não foi possível atualizar a mensagem de progresso do aviso.")

            logger.info(
                "Comunicado privado finalizado (guild=%s, titulo=%s, destinatarios=%s, enviados=%s, falhas=%s).",
                guild.id, titulo, len(membros), enviados, falhas,
            )
            try:
                await interaction.followup.send(
                    f"**Comunicado finalizado: {titulo}**\n"
                    f"• Membros humanos encontrados: **{len(membros)}**\n"
                    f"• DMs enviadas: **{enviados}**\n"
                    f"• Falhas totais: **{falhas}** (permanentes: {permanentes}; temporárias: {falhas - permanentes})\n"
                    f"• Falhas temporárias receberam até {TENTATIVAS_DM} tentativas automáticas.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                logger.exception("Não foi possível publicar o resumo do comunicado.")

        asyncio.create_task(processar_envio_em_segundo_plano())
        await interaction.followup.send(
            f"**Disparo iniciado: {titulo}**\n"
            f"Destinatários: **{len(membros)}** membros humanos.\n"
            "O envio continuará em segundo plano; o Discord ainda pode aplicar limites de entrega.",
            ephemeral=True,
        )

    async def _anunciar_release(self, guild: discord.Guild):
        async with self._lock:
            if self._processando:
                return
            self._processando = True
            try:
                release = self._ler_release()
                if release is None:
                    return

                # Releases oficiais do bot são obrigatórios: não dependem de opt-in.
                # Buscar a lista completa evita limitar o envio aos membros em cache.
                membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
                destinatarios = [str(m.id) for m in membros]
                if not destinatarios:
                    logger.info("Nenhum membro humano encontrado para o release %s.", release["release_id"])
                    return

                estados = await carregar(ARQUIVO_ESTADO, {"guilds": {}})
                if not isinstance(estados, dict):
                    estados = {"guilds": {}}
                estados.setdefault("guilds", {})
                guild_estado = estados["guilds"].setdefault(str(guild.id), {})
                release_estado = guild_estado.setdefault(release["release_id"], {
                    "processados": [],
                    "concluido": False,
                })
                processados = set(str(uid) for uid in release_estado.get("processados", []))
                # Um release concluído pela versão antiga pode ter sido enviado apenas
                # aos inscritos. Só encerrar quando todos os destinatários atuais constarem.
                if release_estado.get("concluido") and all(
                    str(uid) in processados for uid in destinatarios
                ):
                    return
                embed = discord.Embed(
                    description=(
                        "╭────────────── ◈ ──────────────╮\n"
                        "**𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  CENTRAL DE ATUALIZAÇÕES**\n"
                        "╰────────────── ◈ ──────────────╯\n\n"
                        f"**{release['titulo']}**\n"
                        f"{release['mensagem']}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "**◈ O QUE VOCÊ PRECISA SABER**\n"
                        "Esta mensagem resume as novidades publicadas para a gangue. "
                        "Consulte /help ou /tutorial para conhecer os comandos e os sistemas."
                    ),
                    color=0xB3132B,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_author(
                    name="NÊMESIS  •  COMUNICADO OFICIAL",
                    icon_url="https://cdn.discordapp.com/embed/avatars/0.png",
                )
                embed.add_field(
                    name="◈ CATEGORIA",
                    value=f"**{release['tipo']}**",
                    inline=True,
                )
                embed.add_field(
                    name="◈ VERSÃO",
                    value=f"**{release['release_id'][:100]}**",
                    inline=True,
                )
                embed.add_field(
                    name="◈ ACESSO RÁPIDO",
                    value="**/tutorial** — guias dos sistemas\n**/help** — central de comandos\n",
                    inline=False,
                )
                embed.set_footer(
                    text="NÊMESIS • Atualizações oficiais | Envio destinado a todos os membros"
                )

                houve_falha_storage = False
                for user_id in destinatarios:
                    uid = str(user_id)
                    if uid in processados:
                        continue

                    terminal = False
                    try:
                        membro = guild.get_member(int(uid))
                        if membro is None:
                            membro = await guild.fetch_member(int(uid))
                        resultado = await _enviar_dm_com_retry(membro, embed=embed)
                        terminal = resultado in {"enviada", "permanente"}
                        if resultado == "permanente":
                            logger.info(
                                "DM do release indisponível para user=%s; não será repetida para este release.",
                                uid,
                            )
                        elif resultado == "temporaria":
                            logger.warning(
                                "DM do release permanece pendente para user=%s; será tentada em nova inicialização.",
                                uid,
                            )
                    except discord.NotFound:
                        logger.info("Membro %s não está mais no servidor.", uid)
                        terminal = True
                    except (discord.HTTPException, ValueError, TypeError):
                        logger.exception("Falha ao localizar/entregar novidade ao usuário %s.", uid)
                    except Exception:
                        logger.exception("Erro inesperado ao entregar novidade ao usuário %s.", uid)

                    # Só registrar como processado quando entregue ou quando não é
                    # possível entregar permanentemente. Falhas transitórias ficam pendentes.
                    if terminal:
                        processados.add(uid)
                        release_estado["processados"] = sorted(processados)
                        guild_estado[release["release_id"]] = release_estado
                        estados["guilds"][str(guild.id)] = guild_estado
                        try:
                            await salvar(ARQUIVO_ESTADO, estados)
                        except Exception:
                            houve_falha_storage = True
                            logger.exception("Falha ao persistir checkpoint do release %s.", release["release_id"])
                            break
                    await asyncio.sleep(INTERVALO_ENVIO)

                if not houve_falha_storage and all(str(uid) in processados for uid in destinatarios):
                    release_estado["concluido"] = True
                    release_estado["concluido_em"] = datetime.now(timezone.utc).isoformat()
                    guild_estado[release["release_id"]] = release_estado
                    estados["guilds"][str(guild.id)] = guild_estado
                    await salvar(ARQUIVO_ESTADO, estados)
                    logger.info("Entrega do release %s processada para todos os membros humanos.", release["release_id"])
            except Exception:
                logger.exception("Falha ao processar release automático da NÊMESIS.")
            finally:
                self._processando = False

    async def cog_load(self):
        if not self._retry_releases.is_running():
            self._retry_releases.start()

    async def cog_unload(self):
        self._retry_releases.cancel()

    @tasks.loop(minutes=15)
    async def _retry_releases(self):
        # Mantém pendências vivas mesmo sem reinicialização ou reconexão do bot.
        if not CAMINHO_RELEASE.exists():
            return
        guild_id = os.getenv("NEMESIS_GUILD_ID")
        try:
            guild = self.bot.get_guild(int(guild_id)) if guild_id else None
        except (TypeError, ValueError):
            logger.error("NEMESIS_GUILD_ID inválido durante a recuperação de releases.")
            return
        if guild is not None:
            await self._anunciar_release(guild)

    @_retry_releases.before_loop
    async def _before_retry_releases(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        guild_id = os.getenv("NEMESIS_GUILD_ID")
        if not guild_id:
            logger.error("NEMESIS_GUILD_ID não configurado; novidades automáticas ignoradas.")
            return
        try:
            guild_id = int(guild_id)
        except (TypeError, ValueError):
            logger.error("NEMESIS_GUILD_ID inválido; novidades automáticas ignoradas.")
            return
        guild = self.bot.get_guild(guild_id)
        if guild is not None:
            await self._anunciar_release(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(Novidades(bot))
