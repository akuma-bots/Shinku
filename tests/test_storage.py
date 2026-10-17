import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import storage


class TestStorageLocal(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_dir = Path(self.tempdir.name)
        self.patch_dir = patch.object(storage, "DATA_DIR", self.data_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

    def test_rejeita_caminho_fora_do_diretorio_de_dados(self):
        for nome in ("../segredo.json", "/tmp/segredo.json", "subpasta/arquivo.json"):
            with self.subTest(nome=nome):
                with self.assertRaises(storage.ErroStorage):
                    storage._path(nome)

    def test_salvamento_atomico_preserva_json_valido(self):
        destino = storage._path("estado.json")
        storage._salvar_local("estado.json", {"membros": [1, 2, 3]})

        self.assertEqual(json.loads(destino.read_text(encoding="utf-8")), {"membros": [1, 2, 3]})
        self.assertEqual(list(self.data_dir.glob("*.tmp")), [])

    def test_arquivo_ausente_recebe_padrao(self):
        resultado = storage._carregar_local("novo.json", {"ativo": True})
        self.assertEqual(resultado, {"ativo": True})
        self.assertEqual(json.loads((self.data_dir / "novo.json").read_text(encoding="utf-8")), {"ativo": True})


class TestStorageConfiguracao(unittest.IsolatedAsyncioTestCase):
    async def test_chave_do_upstash_isolada_do_site(self):
        self.assertEqual(storage._chave_bot("perfis.json"), "nemesis_bot:perfis.json")

    async def test_importa_dado_antigo_uma_vez_para_namespace_privado(self):
        chamadas = []

        async def redis_mock(*args):
            chamadas.append(args)
            if args == ("GET", "nemesis_bot:perfis.json"):
                return None
            if args == ("GET", "perfis.json"):
                return '{"123": {"xp": 7}}'
            return "OK"

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(storage, "_comando_redis", side_effect=redis_mock):
            resultado = await storage.carregar("perfis.json", {})

        self.assertEqual(resultado, {"123": {"xp": 7}})
        self.assertIn(("SET", "nemesis_bot:perfis.json", '{"123": {"xp": 7}}'), chamadas)

    async def test_upstash_parcial_nao_cai_silenciosamente_no_disco(self):
        with patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", True), patch.object(storage, "USANDO_UPSTASH", False):
            with self.assertRaises(storage.ErroStorage):
                await storage.carregar("estado.json", {})
            with self.assertRaises(storage.ErroStorage):
                await storage.salvar("estado.json", {})


if __name__ == "__main__":
    unittest.main()
