import unittest

from cogs.academia import (
    _avaliar_inscrito,
    _criar_registro_sessao,
    _encerrar_sessao,
    _inscrever,
    _sessoes_do_servidor,
)


class TestAcademia(unittest.TestCase):
    def setUp(self):
        self.sessao = _criar_registro_sessao(
            sessao_id="ACD-ABC123",
            nome="Treinamento de integração",
            descricao="Conteúdo de integração e procedimentos.",
            inicio=2_000_000_000,
            vagas=2,
            criador_id=10,
            agora=100,
        )

    def test_criacao_define_estado_e_limite_de_vagas(self):
        self.assertEqual(self.sessao["status"], "aberta")
        self.assertEqual(self.sessao["vagas"], 2)
        self.assertEqual(self.sessao["inscritos"], {})
        self.assertEqual(self.sessao["criado_por"], 10)

    def test_inscricao_e_idempotente(self):
        sessao, status = _inscrever(self.sessao, 20, agora=110)
        self.assertEqual(status, "inscrito")
        sessao, status = _inscrever(sessao, 20, agora=120)
        self.assertEqual(status, "ja_inscrito")
        self.assertEqual(len(sessao["inscritos"]), 1)

    def test_limite_de_vagas_impede_nova_inscricao(self):
        sessao, _ = _inscrever(self.sessao, 20, agora=110)
        sessao, _ = _inscrever(sessao, 21, agora=111)
        sessao, status = _inscrever(sessao, 22, agora=112)
        self.assertEqual(status, "lotada")
        self.assertEqual(len(sessao["inscritos"]), 2)

    def test_inscricao_nao_acontece_apos_encerramento(self):
        sessao, _ = _encerrar_sessao(self.sessao, agora=110)
        sessao, status = _inscrever(sessao, 20, agora=120)
        self.assertEqual(status, "encerrada")
        self.assertEqual(sessao["inscritos"], {})

    def test_avaliacao_exige_inscricao_previa(self):
        sessao, status = _avaliar_inscrito(
            self.sessao, 20, "aprovado", 10, agora=120
        )
        self.assertEqual(status, "nao_inscrito")
        self.assertEqual(sessao["inscritos"], {})

    def test_avaliacao_registra_resultado_e_responsavel(self):
        sessao, _ = _inscrever(self.sessao, 20, agora=110)
        sessao, status = _avaliar_inscrito(
            sessao, 20, "aprovado", 10, "Concluiu os objetivos.", agora=120
        )
        self.assertEqual(status, "avaliado")
        participante = sessao["inscritos"]["20"]
        self.assertEqual(participante["status"], "aprovado")
        self.assertEqual(participante["avaliado_por"], 10)
        self.assertEqual(participante["observacao"], "Concluiu os objetivos.")

    def test_reavaliacao_preserva_historico_das_avaliacoes(self):
        sessao, _ = _inscrever(self.sessao, 20, agora=110)
        sessao, _ = _avaliar_inscrito(sessao, 20, "reprovado", 10, "Primeira avaliação.", agora=120)
        sessao, _ = _avaliar_inscrito(sessao, 20, "aprovado", 11, "Reavaliação concluída.", agora=130)
        participante = sessao["inscritos"]["20"]
        self.assertEqual(participante["status"], "aprovado")
        self.assertEqual(
            [item["status"] for item in participante["historico_avaliacoes"]],
            ["reprovado", "aprovado"],
        )
        self.assertEqual(participante["historico_avaliacoes"][0]["avaliado_por"], 10)

    def test_resultado_invalido_nao_altera_registro(self):
        sessao, _ = _inscrever(self.sessao, 20, agora=110)
        original = dict(sessao["inscritos"]["20"])
        sessao, status = _avaliar_inscrito(sessao, 20, "promovido", 10, agora=120)
        self.assertEqual(status, "resultado_invalido")
        self.assertEqual(sessao["inscritos"]["20"], original)

    def test_encerramento_preserva_avaliacoes(self):
        sessao, _ = _inscrever(self.sessao, 20, agora=110)
        sessao, _ = _avaliar_inscrito(sessao, 20, "aprovado", 10, agora=120)
        sessao, alterado = _encerrar_sessao(sessao, agora=130)
        self.assertTrue(alterado)
        self.assertEqual(sessao["status"], "encerrada")
        self.assertEqual(sessao["inscritos"]["20"]["status"], "aprovado")
        sessao, alterado = _encerrar_sessao(sessao, agora=140)
        self.assertFalse(alterado)

    def test_leitura_separa_dados_por_servidor(self):
        dados = {
            "1": {"sessoes": {"A": {"id": "A"}}},
            "2": {"sessoes": {"B": {"id": "B"}}},
        }
        self.assertEqual(list(_sessoes_do_servidor(dados, 1)), ["A"])
        self.assertEqual(list(_sessoes_do_servidor(dados, 2)), ["B"])
        self.assertEqual(_sessoes_do_servidor([], 1), {})


if __name__ == "__main__":
    unittest.main()
