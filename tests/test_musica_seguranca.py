import asyncio
import unittest
from unittest.mock import Mock

from cogs.musica import Musica


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


if __name__ == "__main__":
    unittest.main()
