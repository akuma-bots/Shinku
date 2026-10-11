import unittest

from utils.avisos_privados import definir_inscricao, obter_estado_guild


class TestAvisosPrivados(unittest.TestCase):
    def test_inscricao_e_cancelamento(self):
        dados = {"guilds": {}}
        dados, estado = definir_inscricao(dados, 123, 456, True)
        self.assertEqual(estado["inscritos"], ["456"])

        dados, estado = definir_inscricao(dados, 123, 456, False)
        self.assertEqual(estado["inscritos"], [])

    def test_inscricao_nao_duplica_usuario(self):
        dados = {"guilds": {"123": {"inscritos": ["456", 456, "inválido"]}}}
        dados, estado = definir_inscricao(dados, 123, 456, True)
        self.assertEqual(estado["inscritos"], ["456"])

    def test_normalizacao_nao_altera_outro_servidor(self):
        dados = {"guilds": {"111": {"inscritos": ["222"]}, "333": {"inscritos": ["444"]}}}
        dados, _ = definir_inscricao(dados, 111, 555, True)
        self.assertEqual(dados["guilds"]["333"]["inscritos"], ["444"])
        self.assertEqual(dados["guilds"]["111"]["inscritos"], ["222", "555"])

    def test_dados_corrompidos_sao_normalizados(self):
        dados, estado = obter_estado_guild({"guilds": {"123": {"inscritos": "quebrado"}}}, 123)
        self.assertEqual(estado["inscritos"], [])

    def test_ids_invalidos_sao_ignorados(self):
        _, estado = obter_estado_guild({"guilds": {"123": {"inscritos": ["456", "x", None, 456]}}}, 123)
        self.assertEqual(estado["inscritos"], ["456"])


if __name__ == "__main__":
    unittest.main()
