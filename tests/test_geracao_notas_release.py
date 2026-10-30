import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gerar_notas_release.py"
SPEC = importlib.util.spec_from_file_location("gerar_notas_release", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestGeracaoNotasRelease(unittest.TestCase):
    def test_ignora_alteracoes_apenas_de_documentacao_e_testes(self):
        before = "a" * 40
        after = "b" * 40
        original = MOD.git
        try:
            MOD.git = lambda *args: "M\ttests/test_x.py\nM\tREADME.md"
            self.assertEqual(MOD.arquivos_alterados(before, after), [])
        finally:
            MOD.git = original

    def test_classifica_correcao_e_cria_id_unico(self):
        original_git = MOD.git
        original_arquivos = MOD.arquivos_alterados
        try:
            MOD.git = lambda *args: "fix: corrige validação de provas"
            MOD.arquivos_alterados = lambda before, after: [("M", "cogs/revisoes.py")]
            release = MOD.gerar("a" * 40, "b" * 40)
            self.assertEqual(release["tipo"], "Correções")
            self.assertRegex(release["release_id"], r"^\d{8}-\d{6}$")
            self.assertRegex(release["data_atualizacao"], r"^\d{2}/\d{2}/\d{4}$")
            self.assertRegex(release["hora_atualizacao"], r"^\d{2}:\d{2}$")
            self.assertIn("validação de provas", release["mensagem"])
            self.assertNotIn("git-", release["release_id"])
        finally:
            MOD.git = original_git
            MOD.arquivos_alterados = original_arquivos

    def test_ignora_manifesto_para_evitar_loop(self):
        before = "a" * 40
        after = "b" * 40
        original = MOD.git
        try:
            MOD.git = lambda *args: "M\tconfig/novidades.json"
            self.assertEqual(MOD.arquivos_alterados(before, after), [])
        finally:
            MOD.git = original


if __name__ == "__main__":
    unittest.main()
