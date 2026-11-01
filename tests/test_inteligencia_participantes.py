import unittest

from cogs.missoes import _calcular_inteligencia_participantes


class TestInteligenciaParticipantes(unittest.TestCase):
    def setUp(self):
        self.agora = 1_800_000_000
        self.revisoes = [
            {
                "tipo": "missao", "status": "aprovada",
                "autor_id": 101, "auxiliar_id": 202,
                "recompensa_xp": 100, "timestamp": self.agora - 20 * 86400,
                "aprovado_em": self.agora - 20 * 86400,
            },
            {
                "tipo": "especial", "status": "aprovada",
                "autor_id": 101, "recompensa_xp": 50,
                "timestamp": self.agora - 40 * 86400,
                "aprovado_em": self.agora - 40 * 86400,
            },
            {
                "tipo": "contribuicao", "status": "rejeitada",
                "autor_id": 303, "timestamp": self.agora - 30 * 86400,
            },
            {
                "tipo": "missao", "status": "pendente",
                "autor_id": 404, "timestamp": self.agora - 2 * 86400,
            },
            {
                "tipo": "pvp", "status": "aprovada",
                "autor_id": 505, "recompensa_xp": 900,
                "timestamp": self.agora - 1 * 86400,
            },
        ]

    def test_resumo_de_participantes_ignora_outros_tipos(self):
        dados = _calcular_inteligencia_participantes(self.revisoes, self.agora)
        self.assertEqual(dados["total"], 4)
        self.assertEqual(dados["ativos_7d"], 1)
        self.assertEqual(dados["inativos_14d"], 3)

    def test_xp_individual_respeita_divisao_do_auxiliar(self):
        dados = _calcular_inteligencia_participantes(self.revisoes, self.agora)
        self.assertEqual(dados["perfis"]["101"]["xp_missoes"], 110)
        self.assertEqual(dados["perfis"]["101"]["xp_ultimos_30d"], 60)
        self.assertEqual(dados["perfis"]["101"]["xp_30d_anteriores"], 50)
        self.assertEqual(dados["perfis"]["202"]["xp_missoes"], 40)
        self.assertEqual(dados["perfis"]["404"]["xp_missoes"], 0)

    def test_status_e_contagem_por_participante(self):
        dados = _calcular_inteligencia_participantes(self.revisoes, self.agora)
        self.assertEqual(dados["perfis"]["101"]["envios"], 2)
        self.assertEqual(dados["perfis"]["101"]["aprovadas"], 2)
        self.assertEqual(dados["perfis"]["303"]["rejeitadas"], 1)
        self.assertEqual(dados["perfis"]["404"]["pendentes"], 1)

    def test_atividade_recente_e_inatividade_por_ultima_evidencia(self):
        dados = _calcular_inteligencia_participantes(self.revisoes, self.agora)
        ativos = [p["user_id"] for p in dados["mais_ativos"]]
        inativos = [p["user_id"] for p in dados["inativos"]]
        self.assertEqual(ativos, ["404"])
        self.assertEqual(set(inativos), {"101", "202", "303"})
        self.assertEqual(dados["perfis"]["303"]["dias_sem_atividade"], 30)

    def test_data_legada_invalida_nao_interrompe_relatorio(self):
        dados = _calcular_inteligencia_participantes(
            [{"tipo": "missao", "status": "aprovada", "autor_id": 606, "timestamp": "inválida"}],
            self.agora,
        )
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["perfis"]["606"]["ultima_atividade"], None)
        self.assertEqual(dados["inativos_14d"][0]["user_id"], "606")


if __name__ == "__main__":
    unittest.main()
