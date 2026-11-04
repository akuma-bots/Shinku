import unittest

from utils.registro_global import CATEGORIAS


class TestEscopoTopicosRegistroGlobal(unittest.TestCase):
    def test_arquivo_de_membros_fica_restrito_a_ocorrencias_individuais(self):
        descricao = CATEGORIAS["historico_membros"][1].casefold()
        self.assertIn("entradas", descricao)
        self.assertIn("saídas", descricao)
        self.assertNotIn("mensagens editadas", descricao)
        self.assertNotIn("mensagens excluídas", descricao)
        self.assertNotIn("auditoria de cargos", descricao)
        self.assertNotIn("conquistas", descricao)

    def test_comunicacao_nao_promete_publicar_conteudo_de_edicoes_ou_exclusoes(self):
        descricao = CATEGORIAS["mensagens"][1].casefold()
        self.assertIn("anexos", descricao)
        self.assertIn("consulta privada", descricao)
        self.assertNotIn("edições, exclusões", descricao)


if __name__ == "__main__":
    unittest.main()
