import unittest

from cogs.missoes import _calcular_inteligencia_missoes


class TestInteligenciaMissoes(unittest.TestCase):
    def setUp(self):
        self.agora = 1_800_000_000
        self.revisoes = [
            {
                "tipo": "missao", "status": "aprovada",
                "autor_id": 101, "auxiliar_id": 202,
                "recompensa_xp": 100, "timestamp": self.agora - 100,
            },
            {
                "tipo": "especial", "status": "aprovada",
                "autor_id": 101, "recompensa_xp": 50,
                "timestamp": self.agora - 8 * 86400,
            },
            {
                "tipo": "contribuicao", "status": "rejeitada",
                "autor_id": 303, "timestamp": self.agora - 200,
            },
            {
                "tipo": "missao", "status": "pendente",
                "autor_id": 404, "timestamp": self.agora - 300,
            },
            {
                "tipo": "pvp", "status": "aprovada",
                "autor_id": 505, "recompensa_xp": 900,
                "timestamp": self.agora - 50,
            },
            {
                "tipo": "missao", "status": "aprovada",
                "autor_id": 606, "timestamp": self.agora - 50,
            },
        ]

    def test_agrega_status_taxa_e_volume(self):
        dados = _calcular_inteligencia_missoes(self.revisoes, self.agora)
        self.assertEqual(dados["total"], 4)
        self.assertEqual(dados["aprovadas"], 2)
        self.assertEqual(dados["rejeitadas"], 1)
        self.assertEqual(dados["pendentes"], 1)
        self.assertAlmostEqual(dados["taxa_aprovacao"], 200 / 3)

    def test_xp_usa_apenas_recompensas_persistidas_e_divisao_oficial(self):
        dados = _calcular_inteligencia_missoes(self.revisoes, self.agora)
        self.assertEqual(dados["xp_distribuido"], 150)
        self.assertEqual(dados["ranking"], [("101", 110), ("202", 40)])

    def test_atividade_recente_e_participantes(self):
        dados = _calcular_inteligencia_missoes(self.revisoes, self.agora)
        self.assertEqual(dados["participantes"], 5)
        self.assertEqual(dados["ativos_7d"], 4)
        self.assertEqual(dados["envios_7d"], 3)

    def test_separa_metricas_por_categoria(self):
        dados = _calcular_inteligencia_missoes(self.revisoes, self.agora)
        self.assertEqual(
            dados["categorias"]["missao"],
            {"aprovadas": 1, "rejeitadas": 0, "pendentes": 1},
        )
        self.assertEqual(
            dados["categorias"]["contribuicao"]["rejeitadas"],
            1,
        )

    def test_base_sem_decisoes_tem_taxa_zero(self):
        dados = _calcular_inteligencia_missoes(
            [{"tipo": "missao", "status": "pendente", "autor_id": 101}],
            self.agora,
        )
        self.assertEqual(dados["taxa_aprovacao"], 0.0)


if __name__ == "__main__":
    unittest.main()
