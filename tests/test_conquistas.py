import copy
import unittest
from unittest.mock import patch

from utils import conquistas
from cogs.conquistas import montar_estatisticas, _barra


class TestConquistas(unittest.TestCase):
    def test_catalogo_tem_ids_unicos_e_recompensas_nao_negativas(self):
        ids = [item["id"] for item in conquistas.CATALOGO_CONQUISTAS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(item["recompensa_xp"] >= 0 for item in conquistas.CATALOGO_CONQUISTAS))
        self.assertGreaterEqual(len(ids), 12)

    def test_avaliacao_respeita_limites_e_dados_invalidos(self):
        obtidas = conquistas.avaliar_conquistas({
            "xp": 5000,
            "mensagens": "10",
            "missoes": 0,
            "vitorias": 1,
            "mvps": "inválido",
            "maior_sequencia": -1,
        })
        ids = {item["id"] for item in obtidas}
        self.assertIn("primeiro_passo", ids)
        self.assertIn("em_evolucao", ids)
        self.assertIn("presenca_inicial", ids)
        self.assertIn("primeira_vitoria", ids)
        self.assertNotIn("operador", ids)
        self.assertNotIn("primeiro_mvp", ids)

    def test_montagem_estatisticas_conta_apenas_missoes_aprovadas_do_membro(self):
        stats = montar_estatisticas(
            {"xp": 800, "mensagens": 20, "guerras": 2},
            {"vitorias": 4, "mvps": 1, "maior_sequencia": 3},
            [
                {"autor_id": 10, "tipo": "missao", "status": "aprovada"},
                {"autor_id": "10", "tipo": "especial", "status": "aprovada"},
                {"autor_id": 10, "tipo": "pvp", "status": "aprovada"},
                {"autor_id": 10, "tipo": "missao", "status": "pendente"},
                {"autor_id": 20, "tipo": "missao", "status": "aprovada"},
                "inválido",
            ],
            10,
        )
        self.assertEqual(stats, {
            "xp": 800,
            "mensagens": 20,
            "missoes": 2,
            "guerras": 2,
            "vitorias": 4,
            "mvps": 1,
            "maior_sequencia": 3,
        })

    def test_barra_de_progresso_e_limitada(self):
        self.assertEqual(_barra(0, 100), "▱" * 8)
        self.assertEqual(_barra(50, 100), "▰" * 4 + "▱" * 4)
        self.assertEqual(_barra(150, 100), "▰" * 8)


class TestPersistenciaConquistas(unittest.IsolatedAsyncioTestCase):
    async def test_desbloqueio_e_recompensa_ficam_idempotentes(self):
        dados = {}

        async def fake_carregar(_arquivo, _padrao):
            return copy.deepcopy(dados)

        async def fake_salvar(_arquivo, novos):
            nonlocal dados
            dados = copy.deepcopy(novos)

        with patch.object(conquistas, "carregar", fake_carregar), patch.object(
            conquistas, "salvar", fake_salvar
        ):
            estatisticas = {"xp": 1000}
            novos, pendentes = await conquistas.registrar_desbloqueios(1, 2, estatisticas)
            novamente, pendentes_novos = await conquistas.registrar_desbloqueios(1, 2, estatisticas)

            self.assertEqual([item["id"] for item in novos], ["primeiro_passo"])
            self.assertEqual([item["id"] for item in pendentes], ["primeiro_passo"])
            self.assertEqual(novamente, [])
            self.assertEqual([item["id"] for item in pendentes_novos], ["primeiro_passo"])

            marcada = await conquistas.marcar_recompensa_aplicada(1, 2, "primeiro_passo")
            self.assertTrue(marcada)

            _, sem_pendencias = await conquistas.registrar_desbloqueios(1, 2, estatisticas)
            self.assertEqual(sem_pendencias, [])

            registros = await conquistas.listar_desbloqueadas(1, 2)
            self.assertEqual(list(registros), ["primeiro_passo"])
            self.assertEqual(registros["primeiro_passo"]["recompensa_status"], "concluida")


if __name__ == "__main__":
    unittest.main()
