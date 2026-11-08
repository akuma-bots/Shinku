"""Sistema de música por voz para a NÊMESIS.

Requer yt-dlp, PyNaCl e imageio-ffmpeg (FFmpeg empacotado).
Aceita links e buscas; a reprodução depende da disponibilidade do provedor de áudio.
"""
from utils.apresentacao import criar_embed
from utils.storage import atualizar_json, carregar, salvar
import asyncio
import base64
import json
import os
import math
import array
import time
import logging
import random
import shlex
import shutil
import uuid
import unicodedata
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.ext import commands
import imageio_ffmpeg
import yt_dlp

LOG = logging.getLogger(__name__)
MAX_QUEUE = 100
VOLUME_PADRAO = 0.5
ARQUIVO_ESTADO_MUSICA = "estado_musica.json"

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
    "extractor_args": {"youtube": {"player_client": ["android", "ios", "web_safari"]}},
}
FFMPEG_OPCOES = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -sn -dn -loglevel warning",
}


def _garantir_opus() -> bool:
    """Carrega a biblioteca Opus do sistema necessária para enviar áudio ao Discord."""
    try:
        if not discord.opus.is_loaded():
            discord.opus.load_opus("libopus.so.0")
        return discord.opus.is_loaded()
    except Exception:
        LOG.exception("Biblioteca libopus indisponível; a reprodução de voz não funcionará.")
        return False


_SPOTIFY_TOKEN = {"valor": None, "expira_em": 0.0}


def _spotify_json(url: str, token: str | None = None, dados: bytes | None = None,
                  cabecalho: dict | None = None) -> dict:
    headers = dict(cabecalho or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if dados is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    requisicao = Request(url, data=dados, headers=headers)
    with urlopen(requisicao, timeout=15) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _spotify_token_acesso() -> str:
    agora = time.time()
    if _SPOTIFY_TOKEN["valor"] and _SPOTIFY_TOKEN["expira_em"] > agora + 60:
        return _SPOTIFY_TOKEN["valor"]
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "Links do Spotify precisam da integração oficial. Configure SPOTIFY_CLIENT_ID "
            "e SPOTIFY_CLIENT_SECRET nas variáveis privadas do Render."
        )
    credenciais = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token_data = _spotify_json(
        "https://accounts.spotify.com/api/token",
        dados=b"grant_type=client_credentials",
        cabecalho={"Authorization": f"Basic {credenciais}"},
    )
    _SPOTIFY_TOKEN["valor"] = token_data["access_token"]
    _SPOTIFY_TOKEN["expira_em"] = agora + int(token_data.get("expires_in", 3600))
    return _SPOTIFY_TOKEN["valor"]


def _spotify_itens(consulta: str) -> list[dict]:
    """Obtém metadados públicos de faixas Spotify; o áudio será resolvido em fonte reproduzível."""
    parsed = urlparse(consulta)
    partes = [parte for parte in parsed.path.split("/") if parte]
    if parsed.netloc.lower() not in {"open.spotify.com", "www.open.spotify.com"}:
        raise ValueError("Link Spotify inválido.")
    if len(partes) < 2 or partes[0] not in {"track", "album", "playlist", "artist"}:
        raise ValueError("Use um link de faixa, álbum, playlist ou artista do Spotify.")
    tipo, identificador = partes[0], partes[1].split("?")[0]
    token = _spotify_token_acesso()
    itens = []
    if tipo == "track":
        dados = _spotify_json(f"https://api.spotify.com/v1/tracks/{identificador}", token)
        itens = [dados]
    elif tipo == "album":
        dados = _spotify_json(f"https://api.spotify.com/v1/albums/{identificador}/tracks?limit=50", token)
        itens = dados.get("items", [])
        while dados.get("next") and len(itens) < MAX_QUEUE:
            dados = _spotify_json(dados["next"], token)
            itens.extend(dados.get("items", []))
    elif tipo == "artist":
        dados = _spotify_json(
            f"https://api.spotify.com/v1/artists/{identificador}/top-tracks?market=BR",
            token,
        )
        itens = dados.get("tracks", [])
    else:
        url = f"https://api.spotify.com/v1/playlists/{identificador}/tracks?limit=100"
        dados = _spotify_json(url, token)
        itens = [registro.get("track") for registro in dados.get("items", [])]
        while dados.get("next") and len(itens) < MAX_QUEUE:
            dados = _spotify_json(dados["next"], token)
            itens.extend(registro.get("track") for registro in dados.get("items", []))
    resultado = []
    for faixa in itens[:MAX_QUEUE]:
        if not isinstance(faixa, dict) or not faixa.get("name"):
            continue
        artistas = ", ".join(
            str(artista.get("name", "")).strip()
            for artista in faixa.get("artists", []) if isinstance(artista, dict)
        )
        titulo = str(faixa["name"]).strip()
        duracao = max(0, int(faixa.get("duration_ms") or 0) // 1000)
        resultado.append({
            "title": titulo,
            "artist": artistas,
            "duration": duracao,
            "webpage_url": (
                faixa.get("external_urls", {}).get("spotify")
                or f"https://open.spotify.com/track/{faixa.get('id')}"
            ),
        })
    if not resultado:
        raise ValueError("O Spotify não retornou faixas disponíveis para esse link.")
    return resultado


class MusicControlView(discord.ui.View):
    """Painel interativo de reprodução, inspirado em bots de música populares."""

    def __init__(self, cog: "Musica", guild_id: int):
        super().__init__(timeout=1800)
        self.cog = cog
        self.guild_id = guild_id

    async def _validar(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "Este painel pertence a outro servidor.", ephemeral=True
            )
            return False
        return await self.cog._exigir_mesmo_canal(interaction)

    @discord.ui.button(label="Pausar / Retomar", emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def pausar_retomar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        voz = interaction.guild.voice_client
        if voz.is_playing():
            voz.pause()
            await interaction.response.send_message("⏸ Reprodução pausada.", ephemeral=True)
        elif voz.is_paused():
            voz.resume()
            await interaction.response.send_message("▶ Reprodução retomada.", ephemeral=True)
        else:
            await interaction.response.send_message("Não há música tocando agora.", ephemeral=True)

    @discord.ui.button(label="Pular", emoji="⏭️", style=discord.ButtonStyle.primary)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        voz = interaction.guild.voice_client
        if not voz or not (voz.is_playing() or voz.is_paused()):
            await interaction.response.send_message("Não há música para pular.", ephemeral=True)
            return
        self.cog.skip_requested.add(self.guild_id)
        voz.stop()
        await interaction.response.send_message("⏭ Música pulada.", ephemeral=True)

    @discord.ui.button(label="Encerrar", emoji="⏹️", style=discord.ButtonStyle.danger)
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        voz = interaction.guild.voice_client
        self.cog.filas[self.guild_id] = []
        self.cog.loop_modes[self.guild_id] = "off"
        await self.cog._persistir_estado(self.guild_id)
        self.cog.skip_requested.add(self.guild_id)
        if voz:
            if voz.is_playing() or voz.is_paused():
                voz.stop()
            await voz.disconnect(force=True)
        tarefa = self.cog.tarefas.get(self.guild_id)
        if tarefa and not tarefa.done():
            tarefa.cancel()
        self.cog.tarefas.pop(self.guild_id, None)
        await interaction.response.send_message("⏹ Reprodução encerrada e fila limpa.", ephemeral=True)

    @discord.ui.button(label="Embaralhar", emoji="🔀", style=discord.ButtonStyle.secondary)
    async def embaralhar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        fila = self.cog.filas.get(self.guild_id, [])
        if len(fila) < 2:
            await interaction.response.send_message("Adicione pelo menos duas músicas à fila para embaralhar.", ephemeral=True)
            return
        random.shuffle(fila)
        await interaction.response.send_message(f"🔀 Fila embaralhada ({len(fila)} músicas).", ephemeral=True)

    @discord.ui.button(label="Playlists", emoji="🎼", style=discord.ButtonStyle.secondary, row=1)
    async def playlists(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        await self.cog.abrir_playlists(interaction)

    @discord.ui.button(label="Ver fila", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def ver_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        fila = self.cog.filas.get(self.guild_id, [])
        atual = self.cog.agora.get(self.guild_id)
        linhas = []
        if atual:
            linhas.append(f"**Tocando:** [{discord.utils.escape_markdown(atual['title'])}]({atual['webpage_url']})")
        linhas.extend(
            f"**{i}.** {discord.utils.escape_markdown(item.get('title', 'Música'))} · {self.cog._tempo(item.get('duration', 0))}"
            for i, item in enumerate(fila[:20], start=1)
        )
        if len(fila) > 20:
            linhas.append(f"… e mais {len(fila) - 20} música(s).")
        await interaction.response.send_message(
            embed=self.cog._embed_musica("📜 Fila de reprodução", "\n".join(linhas) if linhas else "A fila está vazia."),
            ephemeral=True,
        )

    @discord.ui.button(label="Repetição: desligada", emoji="🔁", style=discord.ButtonStyle.secondary)
    async def repeticao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        modos = ("off", "track", "queue")
        atual = self.cog.loop_modes.get(self.guild_id, "off")
        novo = modos[(modos.index(atual) + 1) % len(modos)]
        self.cog.loop_modes[self.guild_id] = novo
        await self.cog._persistir_estado(self.guild_id)
        rotulos = {"off": "desligada", "track": "música atual", "queue": "fila"}
        button.label = f"Repetição: {rotulos[novo]}"
        await interaction.response.send_message(f"🔁 Repetição definida para **{rotulos[novo]}**.", ephemeral=True)


PLAYLISTS_ARQUIVO = "playlists_musica.json"
MAX_PLAYLISTS_USUARIO = 20
MAX_FAIXAS_PLAYLIST = 100


def _normalizar_faixas_playlist(faixas: list[dict]) -> list[dict]:
    """Mantém apenas metadados estáveis; URLs temporárias de streaming nunca são persistidas."""
    resultado = []
    if not isinstance(faixas, list):
        return resultado
    permitidos = {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be",
        "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com",
        "vimeo.com", "www.vimeo.com", "bandcamp.com", "www.bandcamp.com",
        "twitch.tv", "www.twitch.tv", "mixcloud.com", "www.mixcloud.com",
        "dailymotion.com", "www.dailymotion.com", "deezer.com", "www.deezer.com",
        "music.apple.com", "www.music.apple.com", "tidal.com", "www.tidal.com",
        "open.spotify.com", "www.open.spotify.com",
    }
    for item in faixas[:MAX_FAIXAS_PLAYLIST]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("webpage_url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or (parsed.hostname or "").lower() not in permitidos:
            continue
        try:
            duracao = max(0, int(item.get("duration") or 0))
        except (TypeError, ValueError, OverflowError):
            duracao = 0
        resultado.append({
            "title": str(item.get("title") or "Áudio sem título")[:256],
            "webpage_url": url[:2048],
            "duration": duracao,
        })
    return resultado


async def _listar_playlists(guild_id: int, user_id: int) -> list[dict]:
    dados = await carregar(PLAYLISTS_ARQUIVO, {})
    if not isinstance(dados, dict):
        return []
    por_servidor = dados.get(str(guild_id), {})
    if not isinstance(por_servidor, dict):
        return []
    lista = por_servidor.get(str(user_id), [])
    return [item for item in lista if isinstance(item, dict) and item.get("id")]


async def _salvar_playlist(guild_id: int, user_id: int, nome: str, faixas: list[dict]) -> dict:
    nome = " ".join(str(nome or "").split()).strip()
    if not nome or len(nome) > 50:
        raise ValueError("O nome da playlist deve ter entre 1 e 50 caracteres.")
    normalizadas = _normalizar_faixas_playlist(faixas)
    if not normalizadas:
        raise ValueError("Adicione pelo menos uma música antes de salvar a playlist.")
    resultado = {}

    def transformar(dados):
        resultado.clear()
        if not isinstance(dados, dict):
            dados = {}
        servidor = dados.setdefault(str(guild_id), {})
        if not isinstance(servidor, dict):
            servidor = {}
            dados[str(guild_id)] = servidor
        lista = servidor.setdefault(str(user_id), [])
        if not isinstance(lista, list):
            lista = []
            servidor[str(user_id)] = lista
        existente = next((item for item in lista if str(item.get("nome", "")).casefold() == nome.casefold()), None)
        if existente is not None:
            resultado["erro"] = "duplicada"
            return dados
        if len(lista) >= MAX_PLAYLISTS_USUARIO:
            resultado["erro"] = "limite"
            return dados
        if existente is None:
            playlist = {
                "id": uuid.uuid4().hex[:12],
                "nome": nome,
                "faixas": normalizadas,
                "criado_em": discord.utils.utcnow().timestamp(),
                "atualizado_em": discord.utils.utcnow().timestamp(),
            }
            lista.append(playlist)
            resultado["playlist"] = dict(playlist)
        return dados

    await atualizar_json(PLAYLISTS_ARQUIVO, {}, transformar)
    if resultado.get("erro") == "limite":
        raise ValueError(f"Você já atingiu o limite de {MAX_PLAYLISTS_USUARIO} playlists.")
    if resultado.get("erro") == "duplicada":
        raise ValueError("Já existe uma playlist com esse nome. Escolha outro nome.")
    return resultado["playlist"]


async def _excluir_playlist(guild_id: int, user_id: int, playlist_id: str) -> bool:
    removida = {"valor": False}

    def transformar(dados):
        removida["valor"] = False
        if not isinstance(dados, dict):
            return {}
        servidor = dados.get(str(guild_id), {})
        if not isinstance(servidor, dict):
            return dados
        lista = servidor.get(str(user_id), [])
        if not isinstance(lista, list):
            return dados
        nova = [item for item in lista if str(item.get("id")) != str(playlist_id)]
        removida["valor"] = len(nova) != len(lista)
        servidor[str(user_id)] = nova
        return dados

    await atualizar_json(PLAYLISTS_ARQUIVO, {}, transformar)
    return removida["valor"]


class ModalSalvarPlaylist(discord.ui.Modal):
    def __init__(self, cog: "Musica", guild_id: int, user_id: int):
        super().__init__(title="Salvar fila como playlist")
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.nome = discord.ui.TextInput(
            label="Nome da playlist",
            placeholder="Ex.: Treinos, favoritas, foco...",
            min_length=1,
            max_length=50,
        )
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id or interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta ação pertence a outra pessoa ou servidor.", ephemeral=True)
            return
        faixas = []
        atual = self.cog.agora.get(self.guild_id)
        if atual:
            faixas.append(atual)
        faixas.extend(self.cog.filas.get(self.guild_id, []))
        try:
            playlist = await _salvar_playlist(self.guild_id, self.user_id, self.nome.value, faixas)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=self.cog._embed_musica(
                "🎼 Playlist salva",
                f"**{discord.utils.escape_markdown(playlist['nome'])}**\n"
                f"{len(playlist['faixas'])} música(s) armazenada(s) na sua biblioteca.",
            ),
            ephemeral=True,
        )


class SeletorPlaylist(discord.ui.Select):
    def __init__(self, view: "MusicPlaylistView", playlists: list[dict]):
        self.library = view
        opcoes = [
            discord.SelectOption(
                label=str(item.get("nome") or "Playlist")[:100],
                value=str(item["id"]),
                description=f"{len(item.get('faixas', []))} música(s)"[:100],
                emoji="🎼",
            )
            for item in playlists[:25]
        ]
        super().__init__(
            placeholder="Selecione uma playlist da sua biblioteca",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:musica:playlist_selecionar",
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != self.library.guild_id or interaction.user.id != self.library.user_id:
            await interaction.response.send_message("Esta biblioteca pertence a outra pessoa.", ephemeral=True)
            return
        self.library.playlist_id = self.values[0]
        playlist = next((item for item in self.library.playlists if str(item.get("id")) == self.values[0]), None)
        nome = playlist.get("nome", "Playlist") if playlist else "Playlist"
        self.library.carregar.disabled = playlist is None
        self.library.excluir.disabled = playlist is None
        await interaction.response.edit_message(
            content=f"Playlist selecionada: **{discord.utils.escape_markdown(nome)}**.",
            view=self.library,
        )


class MusicPlaylistView(discord.ui.View):
    def __init__(self, cog: "Musica", guild_id: int, user_id: int, playlists: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.playlists = playlists
        self.playlist_id = None
        if playlists:
            self.add_item(SeletorPlaylist(self, playlists))
        else:
            self.add_item(discord.ui.Button(
                label="Nenhuma playlist salva",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            ))

    async def _validar(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id or interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta biblioteca pertence a outra pessoa ou servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Salvar fila como playlist", emoji="💾", style=discord.ButtonStyle.success, row=1)
    async def salvar_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        await interaction.response.send_modal(ModalSalvarPlaylist(self.cog, self.guild_id, self.user_id))

    @discord.ui.button(label="Carregar na fila", emoji="▶️", style=discord.ButtonStyle.primary, row=1)
    async def carregar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        playlist = next((item for item in self.playlists if str(item.get("id")) == str(self.playlist_id)), None)
        if not playlist:
            await interaction.response.send_message("Selecione uma playlist primeiro.", ephemeral=True)
            return
        faixas = _normalizar_faixas_playlist(playlist.get("faixas", []))
        fila = self.cog.filas.setdefault(self.guild_id, [])
        if len(fila) + len(faixas) > MAX_QUEUE:
            await interaction.response.send_message(
                f"A fila comporta até {MAX_QUEUE} músicas. Remova algumas antes de carregar esta playlist.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        voz = await self.cog._conectar(interaction)
        if voz is None:
            return
        fila.extend({
            **faixa,
            "text_channel_id": interaction.channel_id,
            "http_headers": {},
        } for faixa in faixas)
        await self.cog._garantir_reprodutor(interaction.guild)
        await interaction.followup.send(
            f"▶️ Playlist **{discord.utils.escape_markdown(playlist['nome'])}** carregada: "
            f"**{len(faixas)}** música(s) adicionada(s) à fila.",
            ephemeral=True,
        )

    @discord.ui.button(label="Excluir playlist", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def excluir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        playlist = next((item for item in self.playlists if str(item.get("id")) == str(self.playlist_id)), None)
        if not playlist:
            await interaction.response.send_message("Selecione uma playlist primeiro.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Confirma excluir a playlist **{discord.utils.escape_markdown(playlist['nome'])}**?",
            view=ConfirmarExclusaoPlaylistView(self, self.playlist_id),
            ephemeral=True,
        )


class ConfirmarExclusaoPlaylistView(discord.ui.View):
    def __init__(self, biblioteca: MusicPlaylistView, playlist_id: str):
        super().__init__(timeout=90)
        self.biblioteca = biblioteca
        self.playlist_id = playlist_id

    @discord.ui.button(label="Confirmar exclusão", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != self.biblioteca.guild_id or interaction.user.id != self.biblioteca.user_id:
            await interaction.response.send_message("Somente o proprietário pode excluir esta playlist.", ephemeral=True)
            return
        ok = await _excluir_playlist(self.biblioteca.guild_id, self.biblioteca.user_id, self.playlist_id)
        await interaction.response.edit_message(
            content="Playlist excluída da sua biblioteca." if ok else "A playlist não existe mais.",
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != self.biblioteca.guild_id or interaction.user.id != self.biblioteca.user_id:
            await interaction.response.send_message("Esta confirmação pertence a outra pessoa.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Exclusão cancelada.", view=None)




GUILD_NEMESIS_ID = 1563995879981981817
CANAL_MUSICA_ID = 1563995881508831335
MARCADOR_PAINEL_MUSICA = "NÊMESIS • Painel de música"
ARQUIVO_PAINEL_MUSICA = "painel_musica.json"


class ModalPesquisaMusica(discord.ui.Modal):
    def __init__(self, cog: "Musica", guild_id: int):
        super().__init__(title="Adicionar música à reprodução")
        self.cog = cog
        self.guild_id = guild_id
        self.consulta = discord.ui.TextInput(
            label="Nome da música ou link",
            placeholder="Pesquise uma faixa ou cole um link do YouTube/SoundCloud",
            max_length=300,
        )
        self.add_item(self.consulta)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Este painel pertence à NÊMESIS.", ephemeral=True)
            return
        await self.cog.adicionar_consulta(interaction, self.consulta.value)


class ModalVolumeMusica(discord.ui.Modal):
    def __init__(self, cog: "Musica", guild_id: int):
        super().__init__(title="Ajustar volume")
        self.cog = cog
        self.guild_id = guild_id
        self.percentual = discord.ui.TextInput(label="Volume (1 a 150%)", placeholder="Ex.: 80", min_length=1, max_length=3)
        self.add_item(self.percentual)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Este painel pertence a outro servidor.", ephemeral=True)
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        try:
            valor = int(str(self.percentual.value).strip())
        except ValueError:
            await interaction.response.send_message("Informe um número inteiro entre 1 e 150.", ephemeral=True)
            return
        if not 1 <= valor <= 150:
            await interaction.response.send_message("O volume deve ficar entre 1% e 150%.", ephemeral=True)
            return
        self.cog.volumes[self.guild_id] = valor / 100
        await self.cog._persistir_estado(self.guild_id)
        voz = interaction.guild.voice_client
        if voz and isinstance(voz.source, discord.PCMVolumeTransformer):
            voz.source.volume = valor / 100
        await interaction.response.send_message(f"🔊 Volume ajustado para **{valor}%**.", ephemeral=True)


class MusicPanelView(discord.ui.View):
    """Painel persistente de música; todas as ações são feitas por botões e modais."""

    def __init__(self, cog: "Musica"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _validar_guild(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este painel é exclusivo da NÊMESIS.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Adicionar música", emoji="🔎", style=discord.ButtonStyle.primary,
                       custom_id="nemesis:musica:buscar", row=0)
    async def buscar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._validar_guild(interaction):
            await interaction.response.send_modal(ModalPesquisaMusica(self.cog, GUILD_NEMESIS_ID))

    @discord.ui.button(label="Playlists", emoji="🎼", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:playlists", row=0)
    async def playlists(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._validar_guild(interaction):
            await self.cog.abrir_playlists(interaction)

    @discord.ui.button(label="Ver fila", emoji="📜", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:fila", row=0)
    async def fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        gid = interaction.guild_id
        atual = self.cog.agora.get(gid)
        pendentes = self.cog.filas.get(gid, [])
        linhas = []
        if atual:
            linhas.append(f"**Tocando:** [{discord.utils.escape_markdown(atual['title'])}]({atual['webpage_url']})")
        linhas.extend(
            f"**{indice}.** {discord.utils.escape_markdown(item.get('title', 'Música'))} · "
            f"{self.cog._tempo(item.get('duration', 0))}"
            for indice, item in enumerate(pendentes[:20], start=1)
        )
        if len(pendentes) > 20:
            linhas.append(f"… e mais {len(pendentes) - 20} música(s).")
        await interaction.response.send_message(
            embed=self.cog._embed_musica(
                f"📜 Fila de reprodução · {len(pendentes)} aguardando",
                "\n".join(linhas) if linhas else "A fila está vazia.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Pausar / Retomar", emoji="⏯️", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:pausar", row=1)
    async def pausar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client
        if voz.is_playing():
            voz.pause()
            mensagem = "⏸ Reprodução pausada."
        elif voz.is_paused():
            voz.resume()
            mensagem = "▶ Reprodução retomada."
        else:
            mensagem = "Não há música tocando agora."
        await interaction.response.send_message(mensagem, ephemeral=True)

    @discord.ui.button(label="Pular", emoji="⏭️", style=discord.ButtonStyle.primary,
                       custom_id="nemesis:musica:pular", row=1)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client
        if not (voz.is_playing() or voz.is_paused()):
            await interaction.response.send_message("Não há música para pular.", ephemeral=True)
            return
        self.cog.skip_requested.add(interaction.guild_id)
        voz.stop()
        await interaction.response.send_message("⏭ Música pulada.", ephemeral=True)




    @discord.ui.button(label="Histórico", emoji="🕘", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:historico", row=0)
    async def historico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        recentes = self.cog.historico.get(interaction.guild_id, [])
        linhas = [
            f"**{i}.** {discord.utils.escape_markdown(item.get('title', 'Música'))} · {self.cog._tempo(item.get('duration', 0))}"
            for i, item in enumerate(reversed(recentes[-20:]), start=1)
        ]
        await interaction.response.send_message(
            embed=self.cog._embed_musica("🕘 Reproduzidas recentemente", "\\n".join(linhas) if linhas else "Ainda não há músicas no histórico."),
            ephemeral=True,
        )

    @discord.ui.button(label="Volume", emoji="🔊", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:volume", row=2)
    async def volume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        await interaction.response.send_modal(ModalVolumeMusica(self.cog, GUILD_NEMESIS_ID))

    @discord.ui.button(label="Autoplay: desligado", emoji="♾️", style=discord.ButtonStyle.secondary,
                       custom_id="nemesis:musica:autoplay", row=2)
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        ativo = not self.cog.autoplay.get(interaction.guild_id, False)
        self.cog.autoplay[interaction.guild_id] = ativo
        await self.cog._persistir_estado(interaction.guild_id)
        button.label = "Autoplay: ligado" if ativo else "Autoplay: desligado"
        await interaction.response.send_message(
            "♾️ Autoplay ativado: quando a fila terminar, vou procurar uma faixa relacionada."
            if ativo else "Autoplay desativado.",
            ephemeral=True,
        )

    @discord.ui.button(label="Limpar fila", emoji="🧹", style=discord.ButtonStyle.danger,
                       custom_id="nemesis:musica:limpar_fila", row=2)
    async def limpar_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_guild(interaction):
            return
        if not await self.cog._exigir_mesmo_canal(interaction):
            return
        fila = self.cog.filas.setdefault(interaction.guild_id, [])
        total = len(fila)
        fila.clear()
        await interaction.response.send_message(
            f"🧹 Fila limpa. A música atual continua tocando; {total} faixa(s) removida(s).",
            ephemeral=True,
        )


class AudioDiagnostico(discord.AudioSource):
    """Mede o PCM entregue ao player sem alterar os bytes enviados."""

    def __init__(self, original: discord.AudioSource, guild_id: int, titulo: str):
        self.original = original
        self.guild_id = guild_id
        self.titulo = titulo
        self.frames = 0
        self.bytes_lidos = 0
        self.amostras = 0
        self.amostras_nao_zero = 0
        self.soma_quadrados = 0
        self.pico = 0

    def is_opus(self) -> bool:
        return self.original.is_opus()

    def read(self) -> bytes:
        dados = self.original.read()
        if not dados:
            self._registrar("fim")
            return dados

        self.frames += 1
        self.bytes_lidos += len(dados)
        if len(dados) % 2 == 0:
            amostras = array.array("h")
            amostras.frombytes(dados)
            if amostras:
                pico = max(abs(valor) for valor in amostras)
                self.pico = max(self.pico, pico)
                self.amostras += len(amostras)
                self.amostras_nao_zero += sum(1 for valor in amostras if valor != 0)
                self.soma_quadrados += sum(valor * valor for valor in amostras)

        if self.frames % 250 == 0:
            self._registrar("janela")
        return dados

    def _registrar(self, etapa: str) -> None:
        rms = math.sqrt(self.soma_quadrados / self.amostras) if self.amostras else 0.0
        LOG.info(
            "Diagnóstico PCM (%s): guild=%s, faixa=%s, frames=%s, bytes=%s, "
            "amostras=%s, nao_zero=%s, pico=%s, rms=%.2f.",
            etapa, self.guild_id, self.titulo, self.frames, self.bytes_lidos,
            self.amostras, self.amostras_nao_zero, self.pico, rms,
        )
        self.bytes_lidos = 0
        self.amostras = 0
        self.amostras_nao_zero = 0
        self.soma_quadrados = 0
        self.pico = 0

    def cleanup(self) -> None:
        self.original.cleanup()


class Musica(commands.Cog):
    """Reprodução de música em canais de voz."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.filas: dict[int, list[dict[str, Any]]] = {}
        self.tarefas: dict[int, asyncio.Task] = {}
        self.volumes: dict[int, float] = {}
        self.agora: dict[int, dict[str, Any]] = {}
        self.loop_modes: dict[int, str] = {}
        self.skip_requested: set[int] = set()
        self.autoplay: dict[int, bool] = {}
        self.historico: dict[int, list[dict[str, Any]]] = {}
        self._painel_sync = False
        self._painel_view_registrada = False
        self._estado_lock = asyncio.Lock()
        self.ytdl = yt_dlp.YoutubeDL(YDL_OPCOES)
        self._extrair_lock = asyncio.Lock()
        # Prefere FFmpeg do sistema (Render instala via apt.txt); o binário
        # empacotado pelo imageio-ffmpeg fica como fallback.
        self.ffmpeg = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
        opus_ok = _garantir_opus()
        LOG.info("Reprodução de música usando FFmpeg: %s", self.ffmpeg)
        if not opus_ok:
            LOG.error("Áudio desativado: instale o pacote de sistema libopus0.")

    async def _persistir_estado(self, guild_id: int):
        """Persiste preferências e histórico sem armazenar URLs temporárias de streaming."""
        async with self._estado_lock:
            dados = await carregar(ARQUIVO_ESTADO_MUSICA, {})
            if not isinstance(dados, dict):
                dados = {}
            dados[str(guild_id)] = {
                "autoplay": bool(self.autoplay.get(guild_id, False)),
                "volume": min(1.5, max(0.01, float(self.volumes.get(guild_id, VOLUME_PADRAO)))),
                "loop": self.loop_modes.get(guild_id, "off") if self.loop_modes.get(guild_id) in {"off", "track", "queue"} else "off",
                "historico": [
                    {
                        "title": str(item.get("title") or "Música")[:256],
                        "webpage_url": str(item.get("webpage_url") or "")[:2048],
                        "duration": max(0, int(item.get("duration") or 0)),
                    }
                    for item in self.historico.get(guild_id, [])[-50:]
                    if isinstance(item, dict)
                ],
            }
            await salvar(ARQUIVO_ESTADO_MUSICA, dados)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._painel_sync:
            return
        if not self._painel_view_registrada:
            self.bot.add_view(MusicPanelView(self))
            self._painel_view_registrada = True
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            LOG.warning("Painel musical: servidor NÊMESIS não está disponível.")
            return
        try:
            estados = await carregar(ARQUIVO_ESTADO_MUSICA, {})
            registro_estado = estados.get(str(guild.id), {}) if isinstance(estados, dict) else {}
            if isinstance(registro_estado, dict):
                self.autoplay[guild.id] = bool(registro_estado.get("autoplay", False))
                try:
                    self.volumes[guild.id] = min(1.5, max(0.01, float(registro_estado.get("volume", VOLUME_PADRAO))))
                except (TypeError, ValueError):
                    self.volumes[guild.id] = VOLUME_PADRAO
                modo = registro_estado.get("loop", "off")
                self.loop_modes[guild.id] = modo if modo in {"off", "track", "queue"} else "off"
                historico = registro_estado.get("historico", [])
                self.historico[guild.id] = [
                    item for item in historico[-50:]
                    if isinstance(item, dict) and item.get("webpage_url")
                ] if isinstance(historico, list) else []
            LOG.info("Preferências e histórico musical restaurados para o servidor %s.", guild.id)
        except Exception:
            LOG.exception("Não foi possível restaurar o estado musical do servidor %s.", guild.id)
        canal = guild.get_channel(CANAL_MUSICA_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_MUSICA_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                LOG.exception(
                    "Painel musical: não foi possível acessar o canal configurado %s.",
                    CANAL_MUSICA_ID,
                )
                return
        if not isinstance(canal, discord.TextChannel):
            LOG.error(
                "Painel musical não publicado: o destino %s não é um canal de texto.",
                CANAL_MUSICA_ID,
            )
            return
        permissoes = canal.permissions_for(guild.me) if guild.me else None
        if not permissoes or not (permissoes.view_channel and permissoes.send_messages and permissoes.embed_links):
            LOG.error("Painel musical sem permissões para publicar no canal %s.", canal.id)
            return
        estado = await carregar(ARQUIVO_PAINEL_MUSICA, {})
        estado = estado if isinstance(estado, dict) else {}
        registro = estado.get(str(guild.id), {})
        mensagem = None
        if registro.get("canal_id") == canal.id and registro.get("mensagem_id"):
            try:
                mensagem = await canal.fetch_message(int(registro["mensagem_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem = None
        if mensagem is None and self.bot.user is not None:
            try:
                async for antiga in canal.history(limit=100, oldest_first=False):
                    if antiga.author.id != self.bot.user.id:
                        continue
                    if any(
                        embed.footer and embed.footer.text == MARCADOR_PAINEL_MUSICA
                        for embed in antiga.embeds
                    ):
                        mensagem = antiga
                        break
            except (discord.Forbidden, discord.HTTPException):
                LOG.warning("Painel musical: sem acesso ao histórico do canal %s; será criada uma nova mensagem.", canal.id)
        embed = self._embed_musica(
            "𓂀 CENTRAL MUSICAL",
            "Pesquise músicas, organize sua fila e mantenha suas playlists pessoais. "
            "Entre em um canal de voz antes de iniciar a reprodução.\n\n"
            "**RECURSOS**\n"
            "🔎 Buscar e adicionar faixas\n"
            "🎼 Criar, salvar, carregar e excluir playlists\n"
            "📜 Consultar a fila de reprodução\n"
            "⏯️ Pausar, retomar e pular músicas",
        )
        embed.set_footer(text=MARCADOR_PAINEL_MUSICA)
        view = MusicPanelView(self)
        if mensagem:
            await mensagem.edit(content=None, embed=embed, view=view)
        else:
            mensagem = await canal.send(embed=embed, view=view)
        estado[str(guild.id)] = {"canal_id": canal.id, "mensagem_id": mensagem.id}
        await salvar(ARQUIVO_PAINEL_MUSICA, estado)
        self._painel_sync = True
        LOG.info("Painel musical sincronizado no canal %s (mensagem=%s).", canal.id, mensagem.id)

    async def adicionar_consulta(self, interaction: discord.Interaction, consulta: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use o painel dentro da NÊMESIS.", ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        gid = interaction.guild.id
        if len(self.filas.get(gid, [])) >= MAX_QUEUE:
            await interaction.followup.send(f"A fila atingiu o limite de {MAX_QUEUE} músicas.", ephemeral=True)
            return
        voz = await self._conectar(interaction)
        if voz is None:
            return
        try:
            itens = await self._extrair_varios(consulta)
        except Exception as erro:
            LOG.info("Não foi possível pesquisar áudio: %s", erro)
            await interaction.followup.send(
                f"Não consegui carregar essa fonte musical: {str(erro)[:220]}",
                ephemeral=True,
            )
            return
        fila = self.filas.setdefault(gid, [])
        disponivel = MAX_QUEUE - len(fila)
        if disponivel <= 0:
            await interaction.followup.send(f"A fila atingiu o limite de {MAX_QUEUE} músicas.", ephemeral=True)
            return
        itens = itens[:disponivel]
        for item in itens:
            item["text_channel_id"] = interaction.channel_id
        fila.extend(itens)
        primeira = itens[0]
        posicao = len(fila) - len(itens) + 1
        estado = "Adicionada à fila" if voz.is_playing() or voz.is_paused() else "Preparando reprodução"
        quantidade = f" • {len(itens)} faixa(s)" if len(itens) > 1 else ""
        await interaction.followup.send(
            embed=self._embed_musica(
                f"♫ {estado}",
                f"**[{discord.utils.escape_markdown(primeira['title'])}]({primeira['webpage_url']})**{quantidade}\n"
                f"Duração: {self._tempo(primeira['duration'])} • Posição inicial: {posicao}",
            ),
            ephemeral=True,
        )
        await self._garantir_reprodutor(interaction.guild)


    async def _extrair_varios(self, consulta: str) -> list[dict[str, Any]]:
        """Resolve faixas individuais ou playlists de provedores compatíveis."""
        consulta = str(consulta or "").strip()
        if "open.spotify.com/" in consulta.lower():
            async with self._extrair_lock:
                metadados = await asyncio.to_thread(_spotify_itens, consulta)
                def resolver_spotify():
                    resultado = []
                    for faixa in metadados[:MAX_QUEUE]:
                        busca = f"{faixa['title']} {faixa.get('artist', '')}".strip()
                        dados = self.ytdl.extract_info(f"ytsearch1:{busca}", download=False)
                        entradas = dados.get("entries") if isinstance(dados, dict) else None
                        entrada = next((item for item in entradas or [] if isinstance(item, dict)), None)
                        if not entrada:
                            continue
                        url = str(entrada.get("url") or "").strip()
                        pagina = str(entrada.get("webpage_url") or "").strip()
                        if not url or not pagina:
                            continue
                        resultado.append({
                            "url": url,
                            "title": faixa["title"],
                            "webpage_url": pagina,
                            "duration": faixa["duration"] or int(entrada.get("duration") or 0),
                            "http_headers": entrada.get("http_headers") or {},
                            "source": "Spotify",
                        })
                    return resultado
                itens = await asyncio.to_thread(resolver_spotify)
            if not itens:
                raise ValueError("Não consegui encontrar versões reproduzíveis das faixas desse link Spotify.")
            return itens

        if consulta.startswith(("http://", "https://")):
            def extrair_playlist():
                opcoes = dict(YDL_OPCOES)
                opcoes["noplaylist"] = False
                coletor = yt_dlp.YoutubeDL(opcoes)
                dados = coletor.extract_info(consulta, download=False)
                entradas = dados.get("entries") if isinstance(dados, dict) else None
                if entradas is None:
                    return None
                resultado = []
                for entrada in entradas:
                    if not isinstance(entrada, dict):
                        continue
                    pagina = str(entrada.get("webpage_url") or entrada.get("url") or "").strip()
                    if pagina.startswith(("http://", "https://")):
                        resultado.append(pagina)
                    if len(resultado) >= MAX_QUEUE:
                        break
                return resultado
            async with self._extrair_lock:
                paginas = await asyncio.to_thread(extrair_playlist)
            if paginas is not None:
                itens = []
                for pagina in paginas:
                    try:
                        itens.append(await self._extrair(pagina))
                    except Exception:
                        LOG.warning("Faixa de playlist indisponível: %s", pagina)
                if not itens:
                    raise ValueError("A playlist não possui faixas reproduzíveis.")
                return itens
        return [await self._extrair(consulta)]

    async def abrir_playlists(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("As playlists só funcionam dentro da NÊMESIS.", ephemeral=True)
            return
        playlists = await _listar_playlists(interaction.guild.id, interaction.user.id)
        view = MusicPlaylistView(self, interaction.guild.id, interaction.user.id, playlists)
        descricao = (
            f"Você possui **{len(playlists)} / {MAX_PLAYLISTS_USUARIO}** playlists. "
            "Selecione uma para carregar na fila ou excluir. Você também pode salvar a fila atual."
        )
        await interaction.response.send_message(
            embed=self._embed_musica("🎼 Sua biblioteca musical", descricao),
            view=view,
            ephemeral=True,
        )

    async def _extrair(self, consulta: str) -> dict[str, Any]:
        consulta = str(consulta or "").strip()
        if not consulta:
            raise ValueError("Informe o nome de uma música ou um link válido.")
        if len(consulta) > 300:
            raise ValueError("A pesquisa musical deve ter no máximo 300 caracteres.")

        permitidos = (
            "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be",
            "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com",
            "vimeo.com", "www.vimeo.com", "bandcamp.com", "www.bandcamp.com",
            "twitch.tv", "www.twitch.tv", "mixcloud.com", "www.mixcloud.com",
            "dailymotion.com", "www.dailymotion.com", "deezer.com", "www.deezer.com",
            "music.apple.com", "www.music.apple.com", "tidal.com", "www.tidal.com",
            "open.spotify.com", "www.open.spotify.com",
        )
        if "://" in consulta and not consulta.startswith(("http://", "https://")):
            raise ValueError("O link precisa usar HTTP/HTTPS.")
        if consulta.startswith(("http://", "https://")):
            parsed = urlparse(consulta)
            host = (parsed.hostname or "").lower()
            extensoes_audio = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".m3u", ".pls")
            host_conhecido = any(host == dominio or host.endswith("." + dominio) for dominio in permitidos)
            url_direta = parsed.path.lower().endswith(extensoes_audio)
            if parsed.scheme.lower() not in {"http", "https"} or not (host_conhecido or url_direta):
                raise ValueError("Provedor não permitido: este link ainda não é de uma fonte musical compatível.")

        def extrair():
            spotify = "open.spotify.com/" in consulta.lower()
            if spotify:
                metadados = _spotify_itens(consulta)[0]
                busca = f"{metadados['title']} {metadados.get('artist', '')}".strip()
            elif consulta.startswith(("http://", "https://")):
                busca = None
                dados = self.ytdl.extract_info(consulta, download=False)
            else:
                busca = consulta

            if busca is not None:
                dados = None
                falhas = []
                # A busca tenta YouTube e SoundCloud; falhas de bloqueio, resposta
                # vazia ou ausência de fluxo não encerram a resolução prematuramente.
                for prefixo, provedor in (("ytsearch1:", "YouTube"), ("scsearch1:", "SoundCloud")):
                    try:
                        tentativa = self.ytdl.extract_info(f"{prefixo}{busca}", download=False)
                        entradas = tentativa.get("entries") if isinstance(tentativa, dict) else None
                        candidato = next(
                            (item for item in entradas or [] if isinstance(item, dict) and item.get("url")),
                            None,
                        )
                        if candidato:
                            dados = candidato
                            LOG.info("Faixa resolvida pelo provedor %s.", provedor)
                            break
                        falhas.append(f"{provedor}: nenhum fluxo retornado")
                    except Exception as erro:
                        falhas.append(f"{provedor}: {type(erro).__name__}")
                        LOG.warning("Busca musical falhou no provedor %s: %s", provedor, erro)
                if dados is None:
                    raise ValueError(
                        "Não encontrei um fluxo reproduzível no YouTube nem no SoundCloud. "
                        "Tente outra versão ou um link direto compatível."
                    )

            if not isinstance(dados, dict):
                raise ValueError("O provedor retornou uma resposta inválida.")
            if "entries" in dados:
                entradas = dados.get("entries")
                try:
                    dados = next((item for item in entradas if isinstance(item, dict)), None)
                except TypeError:
                    dados = None
            if not isinstance(dados, dict):
                raise ValueError("Nenhum resultado de áudio foi encontrado.")

            url = str(dados.get("url") or "").strip()
            if urlparse(url).scheme.lower() not in {"http", "https"}:
                raise ValueError("O provedor não retornou um fluxo HTTP/HTTPS válido.")

            titulo = str(dados.get("title") or "Áudio sem título").strip()[:256]
            webpage = str(dados.get("webpage_url") or consulta).strip()[:2048]
            # Para Spotify, mantém o link original apenas como referência de origem;
            # a URL temporária reproduzível continua sendo a retornada pelo YouTube.
            try:
                duracao = max(0, int(dados.get("duration") or 0))
            except (TypeError, ValueError, OverflowError):
                duracao = 0
            headers = dados.get("http_headers")
            return {
                "url": url,
                "title": titulo or "Áudio sem título",
                "webpage_url": webpage,
                "duration": duracao,
                "http_headers": headers if isinstance(headers, dict) else {},
            }

        # YoutubeDL não é thread-safe; uma extração por vez evita disputas entre
        # comandos simultâneos e reduz carga desnecessária nos provedores.
        async with self._extrair_lock:
            return await asyncio.to_thread(extrair)

    @staticmethod
    def _tempo(segundos: int) -> str:
        if segundos <= 0:
            return "desconhecida"
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas}:{minutos:02}:{segundos:02}" if horas else f"{minutos}:{segundos:02}"

    def _embed_musica(self, titulo: str, descricao: str, cor: int = 0xB91C1C) -> discord.Embed:
        embed = criar_embed(title=titulo, description=descricao, color=cor)
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
                    if erro is None:
                        LOG.info(
                            "Processo de áudio finalizado sem erro (guild=%s, faixa=%s).",
                            gid,
                            item.get("title"),
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
                            and "\n" not in str(chave)
                            and "\\r" not in str(valor)
                            and "\n" not in str(valor)
                        ]
                        if linhas:
                            argumentos_headers = "-headers " + shlex.quote("\r\n".join(linhas) + "\r\n")
                    antes = FFMPEG_OPCOES["before_options"]
                    if argumentos_headers:
                        antes = f"{antes} {argumentos_headers}"
                    volume = min(1.5, max(0.01, float(self.volumes.get(gid, VOLUME_PADRAO))))
                    # Decodifica para PCM e deixa o VoiceClient codificar em Opus
                    # usando libopus. Esse caminho evita depender do encoder libopus
                    # embutido no binário FFmpeg do ambiente de hospedagem.
                    fonte_pcm = discord.FFmpegPCMAudio(
                        item["url"],
                        executable=self.ffmpeg,
                        before_options=antes,
                        options=FFMPEG_OPCOES["options"],
                    )
                    fonte_volume = discord.PCMVolumeTransformer(fonte_pcm, volume=volume)

                    # O handshake de voz pode terminar antes da sessão DAVE ficar pronta.
                    # Se o servidor já negociou DAVE, não iniciar envio em texto claro.
                    conexao = getattr(voz, "_connection", None)
                    protocolo_dave = getattr(conexao, "dave_protocol_version", 0)
                    if protocolo_dave > 0 and not getattr(conexao, "can_encrypt", False):
                        LOG.warning(
                            "Sessão DAVE ainda não está pronta; aguardando antes de iniciar áudio "
                            "(guild=%s, protocolo=%s, sessão=%s).",
                            gid, protocolo_dave, getattr(conexao, "dave_session", None) is not None,
                        )
                        limite = asyncio.get_running_loop().time() + 20
                        while (
                            protocolo_dave > 0
                            and not getattr(conexao, "can_encrypt", False)
                            and asyncio.get_running_loop().time() < limite
                        ):
                            await asyncio.sleep(0.25)
                        if protocolo_dave > 0 and not getattr(conexao, "can_encrypt", False):
                            raise RuntimeError(
                                "A sessão segura de voz DAVE não ficou pronta em 20 segundos."
                            )

                    sessao_dave = getattr(conexao, "dave_session", None)
                    LOG.info(
                        "Estado de voz antes do áudio (guild=%s, protocolo_dave=%s, "
                        "sessao_dave=%s, dave_pronto=%s, pode_criptografar=%s, modo=%s).",
                        gid,
                        getattr(conexao, "dave_protocol_version", 0),
                        sessao_dave is not None,
                        getattr(sessao_dave, "ready", False),
                        getattr(conexao, "can_encrypt", False),
                        getattr(voz, "mode", None),
                    )

                    # Mede o PCM e confirma se os datagramas UDP são aceitos pelo socket.
                    # Os contadores permitem separar silêncio na fonte de falha no envio.
                    fonte = AudioDiagnostico(fonte_volume, gid, item.get("title", "Música"))
                    envio = getattr(conexao, "send_packet", None)
                    if conexao is not None and callable(envio):
                        contagem_udp = {"pacotes": 0, "bytes": 0}
                        def enviar_monitorado(pacote):
                            try:
                                resultado = envio(pacote)
                            except OSError:
                                LOG.exception(
                                    "Falha ao enviar pacote UDP de voz (guild=%s, pacote=%s, bytes=%s).",
                                    gid, contagem_udp["pacotes"] + 1, len(pacote),
                                )
                                raise
                            contagem_udp["pacotes"] += 1
                            contagem_udp["bytes"] += len(pacote)
                            if contagem_udp["pacotes"] % 250 == 0:
                                LOG.info(
                                    "Diagnóstico UDP: guild=%s, pacotes=%s, bytes=%s.",
                                    gid, contagem_udp["pacotes"], contagem_udp["bytes"],
                                )
                            return resultado
                        conexao.send_packet = enviar_monitorado

                    LOG.info(
                        "Iniciando transmissão PCM->Opus (guild=%s, faixa=%s, volume=%.2f, "
                        "ffmpeg=%s, opus_carregado=%s, headers=%s).",
                        gid,
                        item.get("title"),
                        volume,
                        self.ffmpeg,
                        discord.opus.is_loaded(),
                        bool(cabecalhos),
                    )
                    voz.play(fonte, after=ao_terminar)
                    LOG.info(
                        "Fonte PCM entregue ao VoiceClient (guild=%s, conectado=%s, "
                        "tocando=%s, canal_voz=%s).",
                        gid,
                        voz.is_connected(),
                        voz.is_playing(),
                        getattr(getattr(voz, "channel", None), "id", None),
                    )
                    canal_texto = self.bot.get_channel(item.get("text_channel_id", 0))
                    if canal_texto:
                        await canal_texto.send(embed=self._embed_musica(
                            "▶ Tocando agora",
                            f"**[{discord.utils.escape_markdown(item['title'])}]({item['webpage_url']})**\n"
                            f"Duração: {self._tempo(item['duration'])}\n"
                            f"Repetição: { {'off': 'desligada', 'track': 'música atual', 'queue': 'fila'}.get(self.loop_modes.get(gid, 'off'), 'desligada') }",
                        ), view=MusicControlView(self, gid))
                    await terminou.wait()
                    historico = self.historico.setdefault(gid, [])
                    historico.append({
                        "title": item.get("title", "Música"),
                        "webpage_url": item.get("webpage_url", ""),
                        "duration": item.get("duration", 0),
                    })
                    del historico[:-50]
                    await self._persistir_estado(gid)
                    # O modo de repetição só é aplicado quando a faixa termina
                    # naturalmente; /skip e o botão Pular não repetem a faixa.
                    if gid in self.skip_requested:
                        self.skip_requested.discard(gid)
                    else:
                        modo_repeticao = self.loop_modes.get(gid, "off")
                        if modo_repeticao == "track":
                            self.filas.setdefault(gid, []).insert(0, item)
                        elif modo_repeticao == "queue":
                            self.filas.setdefault(gid, []).append(item)
                    if (
                        not self.filas.get(gid)
                        and self.autoplay.get(gid, False)
                        and self.loop_modes.get(gid, "off") == "off"
                    ):
                        try:
                            relacionadas = await self._extrair_varios(f"{item.get('title', '')} músicas relacionadas")
                            if relacionadas:
                                proxima = relacionadas[0]
                                proxima["text_channel_id"] = item.get("text_channel_id", 0)
                                self.filas.setdefault(gid, []).append(proxima)
                        except Exception:
                            LOG.exception("Autoplay não conseguiu localizar faixa relacionada no servidor %s.", gid)
                except Exception as erro:
                    # Antes a falha do FFmpeg/VoiceClient podia encerrar a faixa
                    # sem explicar ao membro por que não houve som.
                    LOG.exception("Falha ao iniciar ou manter o áudio no servidor %s.", gid)
                    canal_id = item.get("text_channel_id", 0)
                    canal = self.bot.get_channel(canal_id)
                    if canal:
                        try:
                            detalhe = str(erro).strip().replace("\\n", " ")[:180]
                            await canal.send(
                                "⚠️ Não consegui reproduzir o áudio. "
                                "Verifique se o bot tem as permissões **Conectar** e **Falar** "
                                "no canal de voz e tente outra faixa."
                                + (f"\\nDetalhe técnico: `{discord.utils.escape_markdown(detalhe)}`" if detalhe else "")
                            )
                        except (discord.Forbidden, discord.HTTPException):
                            LOG.warning("Não foi possível enviar o diagnóstico de reprodução no canal %s.", canal_id)
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
            permissoes = estado.channel.permissions_for(interaction.guild.me)
            if not permissoes.connect or not permissoes.speak:
                await interaction.followup.send(
                    "Não tenho as permissões **Conectar** e **Falar** nesse canal de voz.",
                    ephemeral=True,
                )
                return None
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

    async def play(self, interaction: discord.Interaction, consulta: str):
        if not interaction.guild:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        if len(self.filas.get(interaction.guild.id, [])) >= MAX_QUEUE:
            await interaction.followup.send(
                f"A fila atingiu o limite de {MAX_QUEUE} músicas.",
                ephemeral=True,
            )
            return
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

    async def skip(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not (voz.is_playing() or voz.is_paused()):
            await interaction.response.send_message("Não há música tocando agora.", ephemeral=True)
            return
        self.skip_requested.add(interaction.guild.id)
        voz.stop()
        await interaction.response.send_message("⏭ Música pulada.")

    async def pause(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not voz.is_playing():
            await interaction.response.send_message("Não há música tocando para pausar.", ephemeral=True)
            return
        voz.pause()
        await interaction.response.send_message("⏸ Reprodução pausada.")

    async def resume(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        voz = interaction.guild.voice_client if interaction.guild else None
        if not voz or not voz.is_paused():
            await interaction.response.send_message("Não há música pausada.", ephemeral=True)
            return
        voz.resume()
        await interaction.response.send_message("▶ Reprodução retomada.")

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

    async def shuffle(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        fila = self.filas.get(interaction.guild.id, [])
        if len(fila) < 2:
            await interaction.response.send_message("Adicione pelo menos duas músicas à fila.", ephemeral=True)
            return
        random.shuffle(fila)
        await interaction.response.send_message(f"🔀 Fila embaralhada: **{len(fila)}** músicas.")

    async def loop(self, interaction: discord.Interaction, modo: app_commands.Choice[str]):
        if not await self._exigir_mesmo_canal(interaction):
            return
        self.loop_modes[interaction.guild.id] = modo.value
        rotulos = {"off": "desligada", "track": "música atual", "queue": "fila inteira"}
        await interaction.response.send_message(f"🔁 Repetição definida para **{rotulos[modo.value]}**.")

    async def remove(self, interaction: discord.Interaction, posicao: app_commands.Range[int, 1, 100]):
        if not await self._exigir_mesmo_canal(interaction):
            return
        fila = self.filas.get(interaction.guild.id, [])
        if posicao > len(fila):
            await interaction.response.send_message(f"A fila tem apenas **{len(fila)}** música(s).", ephemeral=True)
            return
        item = fila.pop(posicao - 1)
        titulo = discord.utils.escape_markdown(item.get("title", "Música sem título"))
        await interaction.response.send_message(f"🗑️ Removida da fila: **{titulo}**.")

    async def clearqueue(self, interaction: discord.Interaction):
        if not await self._exigir_mesmo_canal(interaction):
            return
        fila = self.filas.setdefault(interaction.guild.id, [])
        total = len(fila)
        fila.clear()
        await interaction.response.send_message(f"🧹 Fila limpa. A música atual continua tocando; **{total}** item(ns) removido(s).")

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
