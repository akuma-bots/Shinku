from utils.apresentacao import criar_embed
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import discord
from discord.ext import commands, tasks

from utils.guild_config import lideranca_only

from utils.storage import carregar, salvar
from utils.preferencias_notificacoes import listar_inscritos
from cogs.boas_vindas_dm import AlternarAvisosButton


logger = logging.getLogger(__name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
ARQUIVO_ESTADO = "novidades_automaticas.json"
CAMINHO_RELEASE = Path(__file__).resolve().parent.parent / "config" / "novidades.json"
CONCORRENCIA_ENVIO = 40
INTERVALO_ENVIO = 1.2  # Mantido apenas para a fila de releases automáticos.
TENTATIVAS_DM = 3
CANAL_ANUNCIOS_ID = 1564076387797569577
GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
CANAL_SISTEMAS_URL = "https://discord.com/channels/1563995879981981817/1563995880833421512"
CANAL_MISSOES_URL = "https://discord.com/channels/1563995879981981817/1563995881315897549"

def _aplicar_identidade_bot(embed: discord.Embed, guild: discord.Guild, bot: discord.Client) -> discord.Embed:
    """Assina os comunicados com o avatar e o banner do próprio bot."""
    usuario = getattr(bot, "user", None)
    avatar = getattr(getattr(usuario, "display_avatar", None), "url", None)
    banner = getattr(getattr(usuario, "banner", None), "url", None)
    banner_servidor = getattr(getattr(guild, "banner", None), "url", None)

    if avatar:
        embed.set_author(name="N̷ÊMESIS  •  COMUNICADO OFICIAL", icon_url=avatar)
        embed.set_thumbnail(url=avatar)
    else:
        embed.set_author(name="N̷ÊMESIS  •  COMUNICADO OFICIAL")

    # Prioriza o banner configurado no perfil do bot; usa o banner do servidor
    # como alternativa quando a aplicação não possui banner próprio.
    if banner or banner_servidor:
        embed.set_image(url=banner or banner_servidor)
    return embed




class NotasDMView(discord.ui.View):
    """Ações úteis dentro da DM da atualização."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Ver sistemas", style=discord.ButtonStyle.link, emoji="📚", url=CANAL_SISTEMAS_URL))
        self.add_item(discord.ui.Button(label="Ver missões", style=discord.ButtonStyle.link, emoji="⚔️", url=CANAL_MISSOES_URL))
        self.add_item(AlternarAvisosButton())


async def _enviar_dm_com_retry(membro: discord.abc.User, *, embed: discord.Embed) -> str:
    """Faz uma única tentativa para evitar duplicações em retries ambíguos."""
    user_id = getattr(membro, "id", "desconhecido")
    try:
        await membro.send(
            embed=embed,
            view=NotasDMView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return "enviada"
    except (discord.Forbidden, discord.NotFound):
        logger.info("DM indisponível permanentemente (user=%s).", user_id)
        return "permanente"
    except (discord.HTTPException, asyncio.TimeoutError, OSError, discord.ConnectionClosed) as erro:
        # Um timeout/erro HTTP pode ocorrer após o Discord aceitar a DM.
        # Não repetir automaticamente para não criar cópias duplicadas.
        logger.warning(
            "Resultado da DM incerto; não haverá reenvio automático (user=%s, erro=%s).",
            user_id, erro, exc_info=True,
        )
        return "temporaria"
    except Exception:
        logger.exception("Erro inesperado ao enviar DM para %s; envio não será repetido.", user_id)
        return "temporaria"


class AvisosPublicosView(discord.ui.View):
    """Atalhos úteis e cancelamento individual de mensagens privadas."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Ver sistemas", style=discord.ButtonStyle.link, emoji="📚", url=CANAL_SISTEMAS_URL))
        self.add_item(discord.ui.Button(label="Ver missões", style=discord.ButtonStyle.link, emoji="⚔️", url=CANAL_MISSOES_URL))
        self.add_item(AlternarAvisosButton())


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
        if release.get("habilitada") is False:
            logger.info("Manifesto atual sem disparo: aguardando uma release importante aprovada pelo gerador.")
            return None
        release_id = str(release.get("release_id", "")).strip()
        titulo = str(release.get("titulo", "")).strip()
        mensagem = str(release.get("mensagem", "")).strip()
        if not release_id or not titulo or not mensagem:
            logger.error("Manifesto de novidades incompleto; release_id, titulo e mensagem são obrigatórios.")
            return None
        gerado_em = str(release.get("gerado_em", "")).strip()
        try:
            instante = datetime.fromisoformat(gerado_em).astimezone(FUSO_HORARIO)
        except (TypeError, ValueError):
            instante = datetime.now(FUSO_HORARIO)
        return {
            "release_id": release_id[:100],
            "titulo": titulo[:200],
            "mensagem": mensagem[:3500],
            "tipo": str(release.get("tipo", "Melhorias dos sistemas"))[:100],
            "data_atualizacao": str(release.get("data_atualizacao") or instante.strftime("%d/%m/%Y"))[:20],
            "hora_atualizacao": str(release.get("hora_atualizacao") or instante.strftime("%H:%M"))[:10],
            "fuso_horario": str(release.get("fuso_horario") or "Horário de Brasília (BRT)")[:50],
        }

    async def _anunciar_release(self, guild: discord.Guild):
        """Entrega uma release uma única vez por membro, com trava persistente antes da DM."""
        async with self._lock:
            if self._processando:
                return
            self._processando = True
            try:
                release = self._ler_release()
                if release is None:
                    return

                estados = await carregar(ARQUIVO_ESTADO, {"guilds": {}})
                if not isinstance(estados, dict):
                    estados = {"guilds": {}}
                guilds = estados.setdefault("guilds", {})
                guild_estado = guilds.setdefault(str(guild.id), {})
                release_estado = guild_estado.setdefault(release["release_id"], {})

                enviados_ids = set(str(x) for x in release_estado.get("dms_enviadas", []))
                indisponiveis_ids = set(str(x) for x in release_estado.get("dms_indisponiveis", []))
                # A reserva é gravada ANTES da chamada ao Discord. Se o processo cair
                # depois da entrega e antes da confirmação, o destinatário não recebe
                # uma segunda cópia na próxima inicialização.
                tentadas_ids = set(str(x) for x in release_estado.get("dms_tentadas", []))
                tentadas_ids.update(enviados_ids)
                tentadas_ids.update(indisponiveis_ids)

                embed = criar_embed(
                    description=(
                        "╭────────────── ◈ ──────────────╮\n"
                        "**𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  NOTAS DE ATUALIZAÇÃO**\n"
                        "╰────────────── ◈ ──────────────╯\n\n"
                        f"**{release['titulo']}**\n"
                        f"{release['mensagem']}\n\n"
                        "**◈ INFORMAÇÕES DA ATUALIZAÇÃO**\n"
                        "Consulte os botões abaixo para acessar os sistemas e acompanhar as missões."
                    ),
                    color=0xB3132B,
                    timestamp=datetime.now(timezone.utc),
                )
                _aplicar_identidade_bot(embed, guild, self.bot)
                embed.add_field(name="◈ CATEGORIA", value=f"**{release['tipo']}**", inline=True)
                embed.add_field(name="◈ DATA", value=f"**{release['data_atualizacao']}**", inline=True)
                embed.add_field(name="◈ HORÁRIO", value=f"**{release['hora_atualizacao']}**\n{release['fuso_horario']}", inline=True)
                embed.set_footer(text=f"NÊMESIS • Atualização em {release['data_atualizacao']} às {release['hora_atualizacao']} (BRT)")

                membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
                inscritos = await listar_inscritos(
                    guild.id, "notas_atualizacao", [str(m.id) for m in membros]
                )
                destinatarios = [
                    membro for membro in membros
                    if str(membro.id) in inscritos
                    and str(membro.id) not in tentadas_ids
                ]

                enviados = 0
                falhas = 0
                for membro in destinatarios:
                    user_id = str(membro.id)

                    # Persistência anterior ao envio: protege contra on_ready duplicado,
                    # reinicializações e retries do ciclo periódico.
                    tentadas_ids.add(user_id)
                    release_estado["dms_tentadas"] = sorted(tentadas_ids)
                    release_estado["ultima_tentativa_em"] = datetime.now(timezone.utc).isoformat()
                    guild_estado[release["release_id"]] = release_estado
                    guilds[str(guild.id)] = guild_estado
                    await salvar(ARQUIVO_ESTADO, estados)

                    resultado = await _enviar_dm_com_retry(membro, embed=embed)
                    if resultado == "enviada":
                        enviados_ids.add(user_id)
                        release_estado["dms_enviadas"] = sorted(enviados_ids)
                        enviados += 1
                    elif resultado == "permanente":
                        indisponiveis_ids.add(user_id)
                        release_estado["dms_indisponiveis"] = sorted(indisponiveis_ids)
                        falhas += 1
                    else:
                        # Resultado de transporte incerto: não repetir automaticamente,
                        # pois o Discord pode ter aceitado a DM antes da perda da resposta.
                        release_estado.setdefault("dms_resultado_incerto", [])
                        incertas = set(str(x) for x in release_estado["dms_resultado_incerto"])
                        incertas.add(user_id)
                        release_estado["dms_resultado_incerto"] = sorted(incertas)
                        falhas += 1

                    release_estado["ultima_tentativa_em"] = datetime.now(timezone.utc).isoformat()
                    guild_estado[release["release_id"]] = release_estado
                    guilds[str(guild.id)] = guild_estado
                    await salvar(ARQUIVO_ESTADO, estados)
                    await asyncio.sleep(INTERVALO_ENVIO)

                release_estado["total_inscritos"] = len(inscritos)
                release_estado["ultimo_envio_em"] = datetime.now(timezone.utc).isoformat()
                release_estado["envio_concluido"] = len(tentadas_ids) >= len(inscritos)
                guild_estado[release["release_id"]] = release_estado
                guilds[str(guild.id)] = guild_estado
                await salvar(ARQUIVO_ESTADO, estados)

                logger.info(
                    "Notas processadas (guild=%s, release=%s, inscritos=%s, enviados_nesta_execucao=%s, falhas=%s, reservas_persistidas=%s).",
                    guild.id, release["release_id"], len(inscritos), enviados, falhas, len(tentadas_ids),
                )
            except Exception:
                logger.exception("Falha ao processar notas automáticas por DM.")
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
        guild_id = os.getenv("NEMESIS_GUILD_ID", str(GUILD_ID))
        try:
            guild = self.bot.get_guild(int(guild_id))
        except (TypeError, ValueError):
            logger.error("NEMESIS_GUILD_ID inválido durante a recuperação de releases.")
            return
        if guild is not None:
            await self._anunciar_release(guild)

    @_retry_releases.before_loop
    async def _before_retry_releases(self):
        await self.bot.wait_until_ready()



async def setup(bot: commands.Bot):
    await bot.add_cog(Novidades(bot))
