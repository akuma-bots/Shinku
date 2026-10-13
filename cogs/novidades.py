import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

from utils.storage import carregar, salvar


logger = logging.getLogger(__name__)
ARQUIVO_INSCRITOS = "avisos_privados.json"
ARQUIVO_ESTADO = "novidades_automaticas.json"
CAMINHO_RELEASE = Path(__file__).resolve().parent.parent / "config" / "novidades.json"
INTERVALO_ENVIO = 1.0


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
                    value="**/tutorial** — guias dos sistemas\n**/help** — central de comandos\n**/avisos-privados** — preferências de DM",
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

                    try:
                        membro = guild.get_member(int(uid))
                        if membro is None:
                            membro = await guild.fetch_member(int(uid))
                        await membro.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                    except discord.Forbidden:
                        logger.info("DM indisponível para membro %s; marcado como processado.", uid)
                    except discord.NotFound:
                        logger.info("Membro %s não está mais no servidor.", uid)
                    except (discord.HTTPException, ValueError, TypeError):
                        logger.exception("Falha ao entregar novidade ao usuário %s.", uid)
                    except Exception:
                        logger.exception("Erro inesperado ao entregar novidade ao usuário %s.", uid)

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
