from utils.apresentacao import criar_embed, COR_PRIMARIA
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

from utils.storage import carregar, atualizar_json
from utils.preferencias_notificacoes import listar_inscritos
from cogs.boas_vindas_dm import AlternarAvisosButton


logger = logging.getLogger(__name__)
FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")
ARQUIVO_ESTADO = "novidades_automaticas.json"
CAMINHO_RELEASE = Path(__file__).resolve().parent.parent / "config" / "novidades.json"
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




class NotasDMView(discord.ui.LayoutView):
    """Cartão Components V2 para as notas automáticas enviadas por DM."""

    def __init__(self, release: dict):
        super().__init__(timeout=None)
        texto = (
            "## 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  NOTAS DE ATUALIZAÇÃO\n"
            f"### {release['titulo']}\n"
            f"{release['mensagem']}\n\n"
            "### ◈ INFORMAÇÕES DA ATUALIZAÇÃO\n"
            f"**Categoria:** {release['tipo']}\n"
            f"**Data:** {release['data_atualizacao']}\n"
            f"**Horário:** {release['hora_atualizacao']} — {release['fuso_horario']}\n\n"
            "Acesse os atalhos para consultar os sistemas e acompanhar as missões."
        )
        sistemas = discord.ui.Button(
            label="Ver sistemas", style=discord.ButtonStyle.link,
            emoji="📚", url=CANAL_SISTEMAS_URL,
        )
        missoes = discord.ui.Button(
            label="Ver missões", style=discord.ButtonStyle.link,
            emoji="⚔️", url=CANAL_MISSOES_URL,
        )
        preferencias = AlternarAvisosButton()
        preferencias.row = None
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(texto),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(sistemas, missoes),
            discord.ui.ActionRow(preferencias),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
            accent_colour=COR_PRIMARIA,
        ))


async def _enviar_dm_com_retry(
    membro: discord.abc.User,
    *,
    view: discord.ui.LayoutView | None = None,
    embed: discord.Embed | None = None,
) -> str:
    """Envia uma única vez; aceita embed legado convertendo-o para cartão V2."""
    if view is None and embed is not None:
        partes = []
        if embed.title:
            partes.append(f"## {embed.title}")
        if embed.description:
            partes.append(embed.description)
        for campo in embed.fields:
            partes.append(f"**{campo.name}**\n{campo.value}")
        if embed.footer and embed.footer.text:
            partes.append(f"-# {embed.footer.text}")
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(
            discord.ui.TextDisplay("\n\n".join(partes)[:3900] or "## NÊMESIS • Comunicado"),
            accent_colour=COR_PRIMARIA,
        ))
    if view is None:
        raise ValueError("É necessário informar um cartão para enviar a DM.")
    user_id = getattr(membro, "id", "desconhecido")
    try:
        await membro.send(
            view=view,
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

    async def cog_load(self):
        # Registra o botão de preferências para que DMs antigas continuem
        # interativas mesmo depois de uma reinicialização da Shinku.
        self.bot.add_view(NotasDMView({
            "titulo": "Atualização",
            "mensagem": "Consulte as notas de atualização da NÊMESIS.",
            "tipo": "Sistema",
            "data_atualizacao": "—",
            "hora_atualizacao": "—",
            "fuso_horario": "America/Sao_Paulo",
        }))

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
            "mensagem": mensagem[:3000],
            "tipo": str(release.get("tipo", "Melhorias dos sistemas"))[:100],
            "data_atualizacao": str(release.get("data_atualizacao") or instante.strftime("%d/%m/%Y"))[:20],
            "hora_atualizacao": str(release.get("hora_atualizacao") or instante.strftime("%H:%M"))[:10],
            "fuso_horario": str(release.get("fuso_horario") or "Horário de Brasília (BRT)")[:50],
        }

    async def _reservar_destinatario_release(self, guild_id: int, release_id: str, user_id: str) -> bool:
        """Reserva o destinatário atomicamente, inclusive entre processos distintos."""
        reserva = {"confirmada": False}

        def aplicar(dados):
            reserva["confirmada"] = False
            if not isinstance(dados, dict):
                dados = {"guilds": {}}
            guilds = dados.setdefault("guilds", {})
            estado_guild = guilds.setdefault(str(guild_id), {})
            estado_release = estado_guild.setdefault(release_id, {})
            tentadas = set(str(x) for x in estado_release.get("dms_tentadas", []))
            tentadas.update(str(x) for x in estado_release.get("dms_enviadas", []))
            tentadas.update(str(x) for x in estado_release.get("dms_indisponiveis", []))
            if user_id in tentadas:
                return dados
            tentadas.add(user_id)
            estado_release["dms_tentadas"] = sorted(tentadas)
            estado_release["ultima_tentativa_em"] = datetime.now(timezone.utc).isoformat()
            estado_guild[release_id] = estado_release
            guilds[str(guild_id)] = estado_guild
            dados["guilds"] = guilds
            reserva["confirmada"] = True
            return dados

        await atualizar_json(ARQUIVO_ESTADO, {"guilds": {}}, aplicar)
        return reserva["confirmada"]

    async def _registrar_resultado_release(self, guild_id: int, release_id: str, user_id: str, resultado: str) -> None:
        """Confirma o resultado sem sobrescrever atualizações concorrentes."""
        def aplicar(dados):
            if not isinstance(dados, dict):
                dados = {"guilds": {}}
            guilds = dados.setdefault("guilds", {})
            estado_guild = guilds.setdefault(str(guild_id), {})
            estado_release = estado_guild.setdefault(release_id, {})
            campo = {
                "enviada": "dms_enviadas",
                "permanente": "dms_indisponiveis",
                "temporaria": "dms_resultado_incerto",
            }.get(resultado, "dms_resultado_incerto")
            valores = set(str(x) for x in estado_release.get(campo, []))
            valores.add(user_id)
            estado_release[campo] = sorted(valores)
            estado_release["ultima_tentativa_em"] = datetime.now(timezone.utc).isoformat()
            estado_guild[release_id] = estado_release
            guilds[str(guild_id)] = estado_guild
            dados["guilds"] = guilds
            return dados

        await atualizar_json(ARQUIVO_ESTADO, {"guilds": {}}, aplicar)

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
                guild_estado = estados.get("guilds", {}).get(str(guild.id), {})
                release_estado = guild_estado.get(release["release_id"], {})
                tentadas_ids = set(str(x) for x in release_estado.get("dms_tentadas", []))
                tentadas_ids.update(str(x) for x in release_estado.get("dms_enviadas", []))
                tentadas_ids.update(str(x) for x in release_estado.get("dms_indisponiveis", []))

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
                    # O CAS impede que duas instâncias reservem o mesmo membro.
                    if not await self._reservar_destinatario_release(guild.id, release["release_id"], user_id):
                        continue

                    resultado = await _enviar_dm_com_retry(membro, view=NotasDMView(release))
                    await self._registrar_resultado_release(guild.id, release["release_id"], user_id, resultado)
                    if resultado == "enviada":
                        enviados += 1
                    else:
                        falhas += 1
                    await asyncio.sleep(INTERVALO_ENVIO)

                def concluir(dados):
                    if not isinstance(dados, dict):
                        dados = {"guilds": {}}
                    guilds = dados.setdefault("guilds", {})
                    estado_guild = guilds.setdefault(str(guild.id), {})
                    estado_release = estado_guild.setdefault(release["release_id"], {})
                    tentadas = set(str(x) for x in estado_release.get("dms_tentadas", []))
                    enviados_ids = set(str(x) for x in estado_release.get("dms_enviadas", []))
                    indisponiveis = set(str(x) for x in estado_release.get("dms_indisponiveis", []))
                    estado_release["total_inscritos"] = len(inscritos)
                    estado_release["ultimo_envio_em"] = datetime.now(timezone.utc).isoformat()
                    estado_release["envio_concluido"] = len(tentadas | enviados_ids | indisponiveis) >= len(inscritos)
                    estado_guild[release["release_id"]] = estado_release
                    guilds[str(guild.id)] = estado_guild
                    dados["guilds"] = guilds
                    return dados

                estado_final = await atualizar_json(ARQUIVO_ESTADO, {"guilds": {}}, concluir)
                estado_release_final = estado_final.get("guilds", {}).get(str(guild.id), {}).get(release["release_id"], {})
                reservas_persistidas = len(set(str(x) for x in estado_release_final.get("dms_tentadas", [])))

                logger.info(
                    "Notas processadas (guild=%s, release=%s, inscritos=%s, enviados_nesta_execucao=%s, falhas=%s, reservas_persistidas=%s).",
                    guild.id, release["release_id"], len(inscritos), enviados, falhas, reservas_persistidas,
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
