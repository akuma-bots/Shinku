import unittest

from cogs.logs import _formatar_linhas_registro


class TestFormatacaoRegistros(unittest.TestCase):
    def test_usa_quebras_de_linha_reais(self):
        self.assertEqual(
            _formatar_linhas_registro(["Autor: 123", "Canal: geral"]),
            "Autor: 123\nCanal: geral",
        )

    def test_ignora_linhas_ausentes_sem_perder_contexto(self):
        self.assertEqual(
            _formatar_linhas_registro(["Autor: 123", None, "Canal: geral"]),
            "Autor: 123\nCanal: geral",
        )

    def test_respeita_limite_de_embed(self):
        self.assertEqual(
            len(_formatar_linhas_registro(["x" * 100], limite=32)),
            32,
        )

    def test_limite_invalido_e_normalizado(self):
        self.assertEqual(_formatar_linhas_registro(["registro"], limite=0), "r")


if __name__ == "__main__":
    unittest.main()
