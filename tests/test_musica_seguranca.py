import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from cogs.musica import (
    Musica,
    MusicPanelView,
    _normalizar_faixas_playlist,
    _salvar_playlist,
)


class TestSegurancaExtracaoMusical(unittest.IsolatedAsyncioTestCase):
    def criar_cog(self, resultado=None):
        cog = object.__new__(Musica)
        cog._extrair_lock = asyncio.Lock()
        cog.ytdl = Mock()
        cog.ytdl.extract_info.return_value = resultado or {
            "url": "https://audio.example/stream",
            "title": "Música",
            "webpage_url": "https://www.youtube.com/watch?v=abc",
            "duration": "120",
            "http_headers": {"User-Agent": "test"},
        }
        return cog

    async def test_rejeita_consulta_vazia(self):
        cog = self.criar_cog()
        with self.assertRaisesRegex(ValueError, "Informe"):
            await cog._extrair("   ")
        cog.ytdl.extract_info.assert_not_called()


    async def test_reconhece_link_spotify_sem_tentar_tratar_como_url_generica(self):
        cog = self.criar_cog()
        with patch("cogs.musica._spotify_itens", return_value=[{
            "title": "Faixa Spotify", "artist": "Artista", "duration": 90,
            "webpage_url": "https://open.spotify.com/track/abc",
        }]), patch.object(cog.ytdl, "extract_info", return_value={
            "entries": [{
                "url": "https://audio.example/stream",
                "title": "Faixa Spotify",
                "webpage_url": "https://www.youtube.com/watch?v=abc",
                "duration": 90,
            }]
        }):
            resultado = await cog._extrair("https://open.spotify.com/track/abc")
        self.assertEqual(resultado["title"], "Faixa Spotify")
        self.assertEqual(resultado["duration"], 90)

    def test_link_spotify_exige_credenciais_quando_nao_configurado(self):
        from cogs.musica import _spotify_itens

        with patch.dict("os.environ", {"SPOTIFY_CLIENT_ID": "", "SPOTIFY_CLIENT_SECRET": ""}):
            with patch("cogs.musica._SPOTIFY_TOKEN", {"valor": None, "expira_em": 0.0}):
                with self.assertRaisesRegex(ValueError, "SPOTIFY_CLIENT_ID"):
                    _spotify_itens("https://open.spotify.com/track/abc")

    async def test_rejeita_url_de_provedor_nao_permitido(self):
        cog = self.criar_cog()
        with self.assertRaisesRegex(ValueError, "não permitido"):
            await cog._extrair("https://example.org/audio")
        cog.ytdl.extract_info.assert_not_called()

    async def test_rejeita_fluxo_local_ou_esquema_nao_http(self):
        cog = self.criar_cog({"url": "file:///etc/passwd", "title": "inválido"})
        with self.assertRaisesRegex(ValueError, "HTTP/HTTPS"):
            await cog._extrair("uma música")

    async def test_normaliza_resultado_valido(self):
        cog = self.criar_cog()
        resultado = await cog._extrair("https://youtu.be/abc")

        self.assertEqual(resultado["duration"], 120)
        self.assertEqual(resultado["title"], "Música")
        self.assertEqual(resultado["http_headers"]["User-Agent"], "test")

    async def test_rejeita_consulta_excessivamente_longa(self):
        cog = self.criar_cog()
        with self.assertRaisesRegex(ValueError, "300 caracteres"):
            await cog._extrair("x" * 301)
        cog.ytdl.extract_info.assert_not_called()

    async def test_aceita_resultados_lazy_do_ytdlp(self):
        cog = self.criar_cog({
            "entries": iter([
                None,
                {
                    "url": "https://audio.example/stream",
                    "title": "Busca",
                    "webpage_url": "https://www.youtube.com/watch?v=abc",
                    "duration": 30,
                },
            ])
        })
        resultado = await cog._extrair("nome da música")

        self.assertEqual(resultado["title"], "Busca")
        self.assertEqual(resultado["duration"], 30)

    def test_verifica_e_carrega_biblioteca_opus_do_sistema(self):
        from cogs.musica import _garantir_opus

        with patch("cogs.musica.discord.opus.is_loaded", side_effect=[False, True]), patch(
            "cogs.musica.discord.opus.load_opus"
        ) as carregar_opus:
            self.assertTrue(_garantir_opus())
        carregar_opus.assert_called_once_with("libopus.so.0")

    def test_retorna_falso_quando_biblioteca_opus_nao_existe(self):
        from cogs.musica import _garantir_opus

        with patch("cogs.musica.discord.opus.is_loaded", return_value=False), patch(
            "cogs.musica.discord.opus.load_opus", side_effect=OSError("missing libopus")
        ):
            self.assertFalse(_garantir_opus())


class TestPlaylistsMusicais(unittest.IsolatedAsyncioTestCase):
    def test_normalizacao_descarta_urls_nao_permitidas_e_nao_guarda_fluxo_temporario(self):
        faixas = _normalizar_faixas_playlist([
            {
                "title": "Faixa válida",
                "webpage_url": "https://youtu.be/abc",
                "url": "https://stream-temporario.example/audio",
                "duration": "123",
            },
            {
                "title": "Arquivo local",
                "webpage_url": "file:///etc/passwd",
                "duration": 10,
            },
        ])
        self.assertEqual(len(faixas), 1)
        self.assertEqual(faixas[0]["title"], "Faixa válida")
        self.assertEqual(faixas[0]["duration"], 123)
        self.assertNotIn("url", faixas[0])

    async def test_salva_playlist_com_metadados_estaveis(self):
        dados = {}

        async def atualizar(_arquivo, _padrao, transformar):
            transformar(dados)

        faixa = {
            "title": "Faixa",
            "webpage_url": "https://www.youtube.com/watch?v=abc",
            "url": "https://stream-temporario.example/audio",
            "duration": 60,
        }
        with patch("cogs.musica.atualizar_json", new=AsyncMock(side_effect=atualizar)):
            playlist = await _salvar_playlist(123, 456, "Favoritas", [faixa])

        self.assertEqual(playlist["nome"], "Favoritas")
        self.assertEqual(len(playlist["faixas"]), 1)
        self.assertNotIn("url", playlist["faixas"][0])
        self.assertEqual(dados["123"]["456"][0]["id"], playlist["id"])

    async def test_nao_sobrescreve_playlist_com_nome_duplicado(self):
        dados = {
            "123": {
                "456": [{
                    "id": "existente",
                    "nome": "Favoritas",
                    "faixas": [{"title": "Original", "webpage_url": "https://youtu.be/abc", "duration": 20}],
                }]
            }
        }

        async def atualizar(_arquivo, _padrao, transformar):
            transformar(dados)

        with patch("cogs.musica.atualizar_json", new=AsyncMock(side_effect=atualizar)):
            with self.assertRaisesRegex(ValueError, "Já existe"):
                await _salvar_playlist(
                    123, 456, "favoritas",
                    [{"title": "Nova", "webpage_url": "https://youtu.be/xyz", "duration": 30}],
                )

    def test_painel_musical_tem_componentes_persistentes(self):
        view = MusicPanelView(object())
        self.assertIsNone(view.timeout)
        custom_ids = {item.custom_id for item in view.children}
        self.assertIn("nemesis:musica:buscar", custom_ids)
        self.assertIn("nemesis:musica:playlists", custom_ids)
        self.assertIn("nemesis:musica:fila", custom_ids)
        self.assertIn("nemesis:musica:historico", custom_ids)
        self.assertIn("nemesis:musica:volume", custom_ids)
        self.assertIn("nemesis:musica:autoplay", custom_ids)
        self.assertIn("nemesis:musica:limpar_fila", custom_ids)




if __name__ == "__main__":
    unittest.main()
