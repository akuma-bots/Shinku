import unittest

from utils.registro_global import CATEGORIAS, GUILD_NEMESIS_ID, CANAL_REGISTRO_GLOBAL_ID


class TestRegistroGlobalNemesis(unittest.TestCase):
    def test_destino_e_exclusivo_da_nemesis(self):
        self.assertEqual(GUILD_NEMESIS_ID, 1563995879981981817)
        self.assertEqual(CANAL_REGISTRO_GLOBAL_ID, 1566579335966498926)

    def test_categorias_essenciais_estao_consolidadas(self):
        esperadas = {
            "mensagens", "atendimento", "moderacao", "historico_membros",
            "operacoes", "administracao", "seguranca", "missoes",
            "competitivo", "eventos", "parcerias", "integracoes",
            "infraestrutura", "sorteios", "sugestoes",
        }
        self.assertEqual(set(CATEGORIAS), esperadas)
        self.assertNotIn("cargos", CATEGORIAS)

    def test_nomes_dos_topicos_sao_unicos(self):
        nomes = [nome for nome, _descricao in CATEGORIAS.values()]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_nomes_sao_claros_e_sem_prefixos_de_versao(self):
        nomes = [nome for nome, _descricao in CATEGORIAS.values()]
        self.assertEqual(len(nomes), 15)
        self.assertTrue(all(not nome.startswith("🆕") for nome in nomes))

    def test_todas_as_categorias_possuem_descricao(self):
        for chave, valor in CATEGORIAS.items():
            with self.subTest(categoria=chave):
                self.assertIsInstance(valor, tuple)
                self.assertEqual(len(valor), 2)
                self.assertTrue(valor[0].strip())
                self.assertTrue(valor[1].strip())


if __name__ == "__main__":
    unittest.main()
