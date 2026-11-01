import unittest

from utils.revisoes import analisar_qualidade


class TestQualidadeMissoes(unittest.TestCase):
    def test_identifica_hash_repetido_sem_rejeitar_protocolos(self):
        digest = "a" * 64
        registros = [
            {"id": "a1", "tipo": "missao", "status": "pendente", "autor_id": 10,
             "timestamp": 9900, "hash_imagem": digest},
            {"id": "b2", "tipo": "especial", "status": "aprovada", "autor_id": 20,
             "timestamp": 9950, "hash_imagem": digest},
        ]
        resultado = analisar_qualidade(registros, agora=10000)
        self.assertEqual(len(resultado["duplicidades"]), 1)
        self.assertTrue(resultado["duplicidades"][0]["entre_participantes"])
        self.assertEqual(registros[0]["status"], "pendente")

    def test_detecta_frequencia_de_envio_em_janela_de_dez_minutos(self):
        registros = [
            {"id": str(i), "tipo": "missao", "status": "pendente", "autor_id": 7,
             "timestamp": 9500 + i * 120}
            for i in range(3)
        ]
        resultado = analisar_qualidade(registros, agora=10000)
        self.assertEqual(resultado["padroes_envio"][0]["autor_id"], "7")
        self.assertEqual(resultado["padroes_envio"][0]["envios_10min"], 3)

    def test_metricas_de_revisor_usam_tempos_validos_e_mediana(self):
        registros = [
            {"id": "1", "tipo": "missao", "status": "aprovada", "autor_id": 1,
             "revisor_id": 9, "timestamp": 9000, "aprovado_em": 9060},
            {"id": "2", "tipo": "missao", "status": "rejeitada", "autor_id": 2,
             "revisor_id": 9, "timestamp": 9000, "rejeitada_em": 10200},
            {"id": "3", "tipo": "missao", "status": "aprovada", "autor_id": 3,
             "revisor_id": 9, "timestamp": 9000, "aprovado_em": "inválido"},
            {"id": "4", "tipo": "missao", "status": "aprovada", "autor_id": 4,
             "revisor_id": 9, "timestamp": 9000, "aprovado_em": float("nan")},
        ]
        resultado = analisar_qualidade(registros, agora=11000)
        revisor = resultado["revisores"][0]
        self.assertEqual(revisor["decisoes"], 2)
        self.assertEqual(revisor["mediana_minutos"], 10.5)
        self.assertEqual(revisor["taxa_rejeicao"], 50.0)

    def test_ignora_pvp_datas_invalidas_e_hash_malformado(self):
        registros = [
            {"id": "pvp", "tipo": "pvp", "status": "aprovada", "autor_id": 1,
             "timestamp": 9900, "hash_imagem": "b" * 64},
            {"id": "bad", "tipo": "missao", "status": "pendente", "autor_id": 2,
             "timestamp": "data ruim", "hash_imagem": "not-a-hash"},
        ]
        resultado = analisar_qualidade(registros, agora=10000)
        self.assertEqual(resultado["evidencias_analisadas"], 0)
        self.assertEqual(resultado["duplicidades"], [])
        self.assertEqual(resultado["padroes_envio"], [])
        self.assertEqual(resultado["revisores"], [])

    def test_alerta_de_rejeicao_exige_amostra_minima(self):
        registros = []
        for i in range(5):
            registros.append({"id": str(i), "tipo": "missao", "status": "rejeitada",
                              "autor_id": i, "revisor_id": 8, "timestamp": 9000 + i,
                              "rejeitada_em": 9100 + i})
        resultado = analisar_qualidade(registros, agora=10000)
        self.assertTrue(resultado["revisores"][0]["alerta_amostra"])


if __name__ == "__main__":
    unittest.main()
