"""Sistema de música por voz para a NÊMESIS.

Requer yt-dlp, PyNaCl e imageio-ffmpeg (FFmpeg empacotado).
Aceita links e buscas; a reprodução depende da disponibilidade do provedor de áudio.
"""
import asyncio
import logging
import shlex
import shutil
from typing import Any
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
import imageio_ffmpeg
import yt_dlp

LOG = logging.getLogger(__name__)
MAX_QUEUE = 100
VOLUME_PADRAO = 0.5

YDL_OPCOES = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_retries": 2,
    "socket_timeout": 15,
    # Tenta clientes públicos alternativos quando o cliente web padrão é bloqueado.
    "extractor_args": {"youtube": {"player_client": ["android", "web_safari"]}},
}
FFMPEG_OPCOES = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -sn -dn -loglevel warning",
}


class Musica(commands.Cog):
    """Reprodução de música em canais de voz."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.filas: dict[int, list[dict[str, Any]]] = {}
        self.tarefas: dict[int, asyncio.Task] = {}
        self.volumes: dict[int, float] = {}
        self.agora: dict[int, dict[str, Any]] = {}
        self.ytdl = yt_dlp.YoutubeDL(YDL_OPCOES)
        # Prefere FFmpeg do sistema (Render instala via apt.txt); o binário
        # empacotado pelo imageio-ffmpeg fica como fallback.
        self.ffmpeg = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
        LOG.info("Reprodução de música usando FFmpeg: %s", self.ffmpeg)

    async def _extrair(self, consulta: str) -> dict[str, Any]:
        # Impede que URLs arbitrárias sejam usadas para acessar serviços internos.
        if consulta.startswith(("http://", "https://")):
            host = (urlparse(consulta).hostname or "").lower()
            permitidos = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be", "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com")
            if not any(host == dominio or host.endswith("." + dominio) for dominio in permitidos):
                raise ValueError("Provedor de música não permitido.")

        def extrair():
            try:
                dados = self.ytdl.extract_info(consulta, download=False)
            except Exception:
                # Para pesquisas por texto, tenta SoundCloud como alternativa
                # quando o YouTube bloqueia a extração. Links não são reescritos.
                if consulta.startswith(("http://", "https://")):
                    raise
                LOG.info("Pesquisa no provedor principal falhou; tentando SoundCloud.")
                dados = self.ytdl.extract_info(f"scsearch1:{consulta}", download=False)
            if "entries" in dados:
                dados = next((item for item in dados["entries"] if item), None)
            if not dados:
                raise ValueError("Nenhum resultado de áudio foi encontrado.")
            url = dados.get("url")
            titulo = dados.get("title") or "Áudio sem título"
            webpage = dados.get("webpage_url") or consulta
            duracao = int(dados.get("duration") or 0)
            if not url:
                raise ValueError("O provedor não retornou um fluxo de áudio.")
            return {
                "url": url,
                "title": titulo,
                "webpage_url": webpage,
                "duration": duracao,
                "http_headers": dados.get("http_headers") or {},
            }
        return await asyncio.to_thread(extrair)

    @staticmethod
    def _tempo(segundos: int) -> str:
        if segundos <= 0:
            return "desconhecida"
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas}:{minutos:02}:{segundos:02}" if horas else f"{minutos}:{segundos:02}"

    def _embed_musica(self, titulo: str, descricao: str, cor: int = 0xB91C1C) -> discord.Embed:
        embed = discord.Embed(title=titulo, description=descricao, color=cor)
        embed.set_footer(text="NÊMESIS • Sistema de música")
        return embed

    async def _tocar_fila(self, guild: discord.Guild):
        gid = guild.id
        try:
            while guild.voice_client and guild.voice_client.is_connected():
                fila = self.filas.setdefault(gid, [])
                if not fila:
                    break
                item = fila.pop(0)
                voz = guild.voice_client
                # Atualiza a URL de mídia perto do momento da reprodução, pois
                # URLs de streaming podem expirar enquanto aguardam na fila.
                try:
                    atualizado = await self._extrair(item["webpage_url"])
                    item["url"] = atualizado["url"]
                    item["http_headers"] = atualizado.get("http_headers") or {}
                except Exception:
                    LOG.exception("Não foi possível atualizar o fluxo de áudio.")
                    canal_texto = self.bot.get_channel(item.get("text_channel_id", 0))
                    if canal_texto:
                        await canal_texto.send(
                            f"Não consegui abrir **{discord.utils.escape_markdown(item['title'])}**. Pulando para a próxima música."
                        )
                    continue
                self.agora[gid] = item
                loop = asyncio.get_running_loop()
                terminou = asyncio.Event()

                def ao_terminar(erro):
                    if erro:
                        LOG.error("Erro de reprodução no servidor %s: %s", gid, erro)
                        canal_id = item.get("text_channel_id", 0)
                        canal = self.bot.get_channel(canal_id)
                        if canal:
                            asyncio.run_coroutine_threadsafe(
                                canal.send(
                                    "⚠️ A fonte de áudio encerrou inesperadamente. "
                                    "Tente outra música ou outro link."
                                ),
                                loop,
                            )
                    loop.call_soon_threadsafe(terminou.set)

                try:
                    # Alguns provedores exigem os mesmos cabeçalhos HTTP usados
                    # pelo yt-dlp para entregar o fluxo de áudio.
                    cabecalhos = item.get("http_headers") or {}
                    argumentos_headers = ""
                    if cabecalhos:
                        linhas = [
                            f"{chave}: {valor}"
                            for chave, valor in cabecalhos.items()
                            if "\\r" not in str(chave)
                            and "\\n" not in str(chave)
                            and "\\r" not in str(valor)
                            and "\\n" not in str(valor)
                        ]
                        if linhas:
                            argumentos_headers = "-headers " + shlex.quote("\r\n".join(linhas) + "\r\n")
                    antes = FFMPEG_OPCOES["before_options"]
                    if argumentos_headers:
                        antes = f"{antes} {argumentos_headers}"
                    fonte = discord.FFmpegPCMAudio(
                        item["url"],
                        executable=self.ffmpeg,
                        before_options=antes,
                        options=FFMPEG_OPCOES["options"],
                    )
                    volume = self.volumes.get(gid, VOLUME_PADRAO)
                    voz.play(discord.PCMVolumeTransformer(fonte, volume=volume), after=ao_terminar)
                    canal_texto = self.bot.get_channel(item.get("text_channel_id", 0))
                    if canal_texto:
                        await canal_texto.send(embed=self._embed_musica(
                            "▶ Tocando agora",
                            f"**[{discord.utils.escape_markdown(item['title'])}]({item['webpage_url']})**\n"
                            f"Duração: {self._tempo(item['duration'])}",
                        ))
                    await terminou.wait()
                except (discord.HTTPException, discord.ClientException, OSError):
                    LOG.exception("Falha ao reproduzir áudio no servidor %s.", gid)
                finally:
                    if self.agora.get(gid) is item:
                        self.agora.pop(gid, None)
        finally:
            # Só a tarefa atual pode remover sua própria referência.
            if self.tarefas.get(gid) is asyncio.current_task():
                self.tarefas.pop(gid, None)
            # Evita perder uma música adicionada no instante em que a fila esvaziou.
            if (
                self.filas.get(gid)
                and guild.voice_client
                and guild.voice_client.is_connected()
            ):
                await self._garantir_reprodutor(guild)

    async def _garantir_reprodutor(self, guild: discord.Guild):
        tarefa = self.tarefas.get(guild.id)
        if tarefa is None or tarefa.done():
            self.tarefas[guild.id] = asyncio.create_task(self._tocar_fila(guild))

    async def _conectar(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Este comando só funciona dentro de um servidor.", ephemeral=True)
            return None
        estado = interaction.user.voice
        if not estado or not estado.channel:
            await interaction.followup.send("Entre em um canal de voz primeiro.", ephemeral=True)
            return None
        voz = interaction.guild.voice_client
        try:
            if voz and voz.is_connected():
                if voz.channel != estado.channel:
                    await interaction.followup.send(
                        f"Já estou tocando em {voz.channel.mention}. Entre nesse canal para controlar a reprodução.",
                        ephemeral=True,
                    )
                    return None
            else:
                voz = await estado.channel.connect(timeout=15, reconnect=True)
        except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
            LOG.exception("Não foi possível conectar ao canal de voz.")
            await interaction.followup.send(
                "Não consegui entrar no canal de voz. Confira as permissões Conectar e Falar.",
                ephemeral=True,
            )
            return None
        return voz

    async def _exigir_mesmo_canal(self, interaction: discord.Interaction) -> bool:
        """Evita que membros de outro canal controlem a sessão de música."""
        guild = interaction.guild
        voz = guild.voice_client if guild else None
        membro = interaction.user
        estado = membro.voice if isinstance(membro, discord.Member) else None
        if not voz or not voz.is_connected():
            await interaction.response.send_message(
                "Não há uma sessão de música conectada.", ephemeral=True
            )
            return False
        if not estado or estado.channel != voz.channel:
            await interaction.response.send_message(
                f"Entre em {voz.channel.mention} para controlar a música.", ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="play", description="Toca uma música por link ou pesquisa.")
    @app_commands.describe(consulta="Nome da música ou URL do áudio/vídeo")
    async def play(self, interaction: discord.Interaction, consulta: str):
        if not interaction.guild:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        voz = await self._conectar(interaction)
        if voz is None:
            return
        try:
            item = await self._extrair(consulta)
        except (Exception, asyncio.TimeoutError) as erro:
            LOG.info("Não foi possível pesquisar áudio: %s", erro)
            await interaction.followup.send(
                "Não encontrei essa música ou o provedor bloqueou a consulta. Tente outro nome ou link.",
                ephemeral=True,
            )
            return
        item["text_channel_id"] = interaction.channel_id
        fila = self.filas.setdefault(interaction.guild.id, [])
        if len(fila) >= MAX_QUEUE:
            await interaction.followup.send(
                f"A fila atingiu o limite de {MAX_QUEUE} músicas.", ephemeral=True
            )
            return
        fila.append(item)
        posicao = len(fila)
        if voz.is_playing() or voz.is_paused() or self.tarefas.get(interaction.guild.id, None):
            await interaction.followup.send(embed=self._embed_musica(
                "♫ Adicionada à fila",
                f"**[{discord.utils.escape_markdown(item['title'])}]({item['webpage_url']})**\n"
                f"Duração: {self._tempo(item['duration'])} • Posição na fila: {posicao}",
            ))
        else:
            await interaction.followup.send(embed=self._embed_musica(
                "♫ Preparando reprodução",
                f"**[{discord.utils.escape_markdown(item['title'])}]({item['webpage_url']})**",
            ))
        await self._garantir_reprodutor(interaction.guild)

    @app_commands.command(name="skip", description="Pula a música atual.")
    async def skip(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not (voz.is_playing() or voz.is_paused()):
            await interaction.response.send_message("Não há música tocando agora.", ephemeral=True)
            return
        voz.stop()
        await interaction.response.send_message("⏭ Música pulada.")

    @app_commands.command(name="pause", description="Pausa a música atual.")
    async def pause(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not voz.is_playing():
            await interaction.response.send_message("Não há música tocando para pausar.", ephemeral=True)
            return
        voz.pause()
        await interaction.response.send_message("⏸ Reprodução pausada.")

    @app_commands.command(name="resume", description="Retoma a música pausada.")
    async def resume(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not voz.is_paused():
            await interaction.response.send_message("Não há música pausada.", ephemeral=True)
            return
        voz.resume()
        await interaction.response.send_message("▶ Reprodução retomada.")

    @app_commands.command(name="queue", description="Mostra a fila de músicas.")
    async def queue(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        fila = self.filas.get(interaction.guild.id, [])
        if not fila:
            await interaction.response.send_message(embed=self._embed_musica(
                "♫ Fila de reprodução", "A fila está vazia."
            ))
            return
        linhas = [
            f"**{i}.** {discord.utils.escape_markdown(item['title'])} — {self._tempo(item['duration'])}"
            for i, item in enumerate(fila[:15], start=1)
        ]
        if len(fila) > 15:
            linhas.append(f"… e mais {len(fila) - 15} música(s).")
        await interaction.response.send_message(embed=self._embed_musica(
            f"♫ Fila de reprodução ({len(fila)})", "\n".join(linhas)
        ))

    @app_commands.command(name="nowplaying", description="Mostra o estado da reprodução atual.")
    async def nowplaying(self, interaction: discord.Interaction):
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not (voz.is_playing() or voz.is_paused()):
            await interaction.response.send_message("Não há música tocando agora.", ephemeral=True)
            return
        estado = "Pausada" if voz.is_paused() else "Tocando"
        atual = self.agora.get(interaction.guild.id, {})
        titulo = discord.utils.escape_markdown(atual.get("title", "Música atual"))
        duracao = self._tempo(atual.get("duration", 0))
        await interaction.response.send_message(embed=self._embed_musica(
            "♫ Estado da reprodução",
            f"**{titulo}**\nEstado: **{estado}** • Duração: **{duracao}**\n"
            f"Fila restante: **{len(self.filas.get(interaction.guild.id, []))}**"
        ))

    @app_commands.command(name="volume", description="Ajusta o volume da música (1–100%).")
    @app_commands.describe(percentual="Volume de 1 a 100")
    async def volume(self, interaction: discord.Interaction, percentual: app_commands.Range[int, 1, 100]):
        if not interaction.guild:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        if not await self._exigir_mesmo_canal(interaction):
            return
        gid = interaction.guild.id
        self.volumes[gid] = percentual / 100
        voz = interaction.guild.voice_client
        if voz and isinstance(voz.source, discord.PCMVolumeTransformer):
            voz.source.volume = percentual / 100
        await interaction.response.send_message(f"🔊 Volume definido para **{percentual}%**.")

    @app_commands.command(name="stop", description="Para a música, limpa a fila e sai do canal de voz.")
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        if not await self._exigir_mesmo_canal(interaction):
            return
        gid = interaction.guild.id
        self.filas[gid] = []
        voz = interaction.guild.voice_client
        if voz:
            if voz.is_playing() or voz.is_paused():
                voz.stop()
            await voz.disconnect(force=True)
        tarefa = self.tarefas.get(gid)
        if tarefa and not tarefa.done():
            tarefa.cancel()
        self.tarefas.pop(gid, None)
        await interaction.response.send_message("⏹ Reprodução encerrada; fila limpa e bot desconectado.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Musica(bot))
