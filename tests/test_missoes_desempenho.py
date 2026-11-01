import unittest

from cogs.missoes import _resumir_desempenho_missoes, _ranking_xp_missoes


class TestDesempenhoMissoes(unittest.TestCase):
    def setUp(self):
        self.revisoes = [
            {
                "id": "REV-01", "tipo": "missao", "status": "aprovada",
                "autor_id": 101, "auxiliar_id": 202, "recompensa_xp": 60,
                "titulo": "Operação conjunta", "aprovado_em": 100,
            },
            {
                "id": "REV-02", "tipo": "especial", "status": "aprovada",
                "autor_id": 101, "recompensa_xp": 40, "titulo": "Operação solo",
                "aprovado_em": 200,
            },
            {
                "id": "REV-03", "tipo": "contribuicao", "status": "rejeitada",
                "autor_id": 202, "titulo": "Contribuição recusada", "rejeitada_em": 300,
                "motivo_rejeicao": "Evidência incompleta para validação.",
            },
            {
                "id": "REV-04", "tipo": "missao", "status": "pendente",
                "autor_id": 101, "titulo": "Em análise", "timestamp": 400,
            },
            {
                "id": "REV-05", "tipo": "pvp", "status": "aprovada",
                "autor_id": 303, "recompensa_xp": 999,
            },
            {
                "id": "REV-06", "tipo": "missao", "status": "aprovada",
                "autor_id": 404, "titulo": "Registro legado",
            },
        ]

    def test_resumo_considera_responsavel_auxiliar_e_status(self):
        resumo = _resumir_desempenho_missoes(self.revisoes, 101)
        self.assertEqual(resumo["aprovadas"], 2)
        self.assertEqual(resumo["rejeitadas"], 0)
        self.assertEqual(resumo["pendentes"], 1)
        self.assertEqual(resumo["xp_missoes"], 76)
        self.assertEqual(resumo["registros_com_xp"], 2)
        self.assertEqual(resumo["recentes"][0]["id"], "REV-04")
        self.assertEqual(len(resumo["historico"]), 3)
        self.assertEqual(resumo["historico"][0]["id"], "REV-04")

    def test_auxiliar_recebe_parcela_correspondente_da_recompensa(self):
        resumo = _resumir_desempenho_missoes(self.revisoes, 202)
        self.assertEqual(resumo["aprovadas"], 1)
        self.assertEqual(resumo["rejeitadas"], 1)
        self.assertEqual(resumo["xp_missoes"], 24)

    def test_ranking_soma_recompensas_sem_estimar_registros_legados(self):
        ranking = _ranking_xp_missoes(self.revisoes)
        self.assertEqual(ranking, [("101", 76), ("202", 24)])


    def test_data_legada_invalida_nao_interrompe_a_ordenacao(self):
        revisoes = [
            {
                "id": "REV-BAD", "tipo": "missao", "status": "pendente",
                "autor_id": 101, "timestamp": "data-invalida",
            },
            {
                "id": "REV-OK", "tipo": "missao", "status": "pendente",
                "autor_id": 101, "timestamp": 500,
            },
        ]
        resumo = _resumir_desempenho_missoes(revisoes, 101)
        self.assertEqual(
            [item["id"] for item in resumo["historico"]],
            ["REV-OK", "REV-BAD"],
        )

    def test_historico_preserva_justificativa_de_rejeicao(self):
        resumo = _resumir_desempenho_missoes(self.revisoes, 202)
        rejeitada = next(
            item for item in resumo["historico"]
            if item["status"] == "rejeitada"
        )
        self.assertEqual(
            rejeitada["motivo_rejeicao"],
            "Evidência incompleta para validação.",
        )


if __name__ == "__main__":
    unittest.main()
