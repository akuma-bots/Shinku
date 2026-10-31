import unittest

from cogs.perfil import _posicao_progressao, _resumo_historico_missoes, _resumo_progressao


class TestPerfilIntegrado(unittest.TestCase):
    def test_resumo_progressao_separa_xp_e_postos_organizacionais(self):
        resumo = _resumo_progressao({
            "xp": 900,
            "mensagens": 12,
            "missoes": 3,
            "guerras": 2,
        })

        self.assertEqual(resumo["xp"], 900)
        self.assertEqual(resumo["rank"]["nome"], "Subtenente")
        self.assertEqual(resumo["proximo"]["nome"], "Tenente")
        self.assertEqual(resumo["faltam"], 1300)
        self.assertEqual(resumo["mensagens"], 12)
        self.assertEqual(resumo["missoes"], 3)
        self.assertEqual(resumo["guerras"], 2)

    def test_resumo_progressao_trata_dados_legados_invalidos(self):
        resumo = _resumo_progressao({
            "xp": "inválido",
            "mensagens": None,
            "missoes": "x",
            "guerras": -4,
        })

        self.assertEqual(resumo["xp"], 0)
        self.assertEqual(resumo["mensagens"], 0)
        self.assertEqual(resumo["missoes"], 0)
        self.assertEqual(resumo["guerras"], 0)
        self.assertEqual(resumo["rank"]["nome"], "Lutador")

    def test_historico_filtra_membro_conta_status_e_ordena_recente(self):
        registros = [
            {"id": "a", "autor_id": 10, "status": "aprovada", "titulo": "Missão A", "aprovado_em": 100},
            {"id": "b", "autor_id": "10", "status": "rejeitada", "titulo": "Missão B", "rejeitada_em": 300},
            {"id": "c", "autor_id": 20, "status": "aprovada", "titulo": "Outro membro", "aprovado_em": 500},
            {"id": "d", "autor_id": 10, "status": "pendente", "titulo": "Missão D", "timestamp": 200},
            "registro-inválido",
        ]

        resumo = _resumo_historico_missoes(registros, 10, limite=2)

        self.assertEqual(resumo["aprovadas"], 1)
        self.assertEqual(resumo["rejeitadas"], 1)
        self.assertEqual(resumo["pendentes"], 1)
        self.assertEqual([item["id"] for item in resumo["recentes"]], ["b", "d"])

    def test_posicao_progressao_ordena_por_xp_e_participacao(self):
        membros = {
            "10": {"xp": 100, "mensagens": 8},
            "20": {"xp": 200, "mensagens": 1},
            "30": {"xp": 100, "mensagens": 12},
        }

        self.assertEqual(_posicao_progressao(membros, 20), 1)
        self.assertEqual(_posicao_progressao(membros, 30), 2)
        self.assertEqual(_posicao_progressao(membros, 10), 3)
        self.assertIsNone(_posicao_progressao(membros, 99))

    def test_historico_vazio_nao_cria_registros(self):
        resumo = _resumo_historico_missoes([], 10)

        self.assertEqual(resumo, {
            "aprovadas": 0,
            "rejeitadas": 0,
            "pendentes": 0,
            "recentes": [],
        })


if __name__ == "__main__":
    unittest.main()
