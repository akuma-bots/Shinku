import unittest

from cogs.contadores import _contador_registrado


class TestSegurancaContadores(unittest.TestCase):
    def test_reconhece_canal_registrado(self):
        config = {"contadores": [{"canal_id": 123, "tipo": "membros"}]}
        self.assertTrue(_contador_registrado(config, 123))

    def test_nao_apaga_canal_que_nao_e_contador(self):
        config = {"contadores": [{"canal_id": 123, "tipo": "membros"}]}
        self.assertFalse(_contador_registrado(config, 456))

    def test_ignora_configuracao_corrompida(self):
        self.assertFalse(_contador_registrado([], 123))
        self.assertFalse(_contador_registrado({"contadores": [None, "inválido"]}, 123))


if __name__ == "__main__":
    unittest.main()
