import unittest
from unittest.mock import AsyncMock, patch

from utils import revisoes


class TestAuditoriaIntegridade(unittest.TestCase):
    def test_protocolo_valido_com_trilha_nao_gera_ocorrencias(self):
        protocolo = {
            "id": "abc123", "guild_id": 10, "tipo": "missao",
            "status": "aprovada", "autor_id": 20, "revisor_id": 30,
            "timestamp": 1000, "criado_em": 1000,
            "aprovado_em": 1100, "atualizado_em": 1100,
            "recompensa_xp": 250,
            "trilha_auditoria": [
                {"evento": "protocolo_criado", "em": 1000, "status_novo": "pendente"},
                {"evento": "protocolo_aprovado", "em": 1100, "status_novo": "aprovada"},
            ],
        }
        resultado = revisoes.analisar_integridade([protocolo], guild_id=10, agora=1200)
        self.assertEqual(resultado["total_ocorrencias"], 0)
        self.assertEqual(resultado["integridade_percentual"], 100.0)

    def test_detecta_aprovacao_sem_revisor_e_trilha_divergente(self):
        protocolo = {
            "id": "abc123", "tipo": "missao", "status": "aprovada",
            "timestamp": 1000, "aprovado_em": 1100,
            "trilha_auditoria": [{"evento": "protocolo_criado", "em": 1000, "status_novo": "pendente"}],
        }
        resultado = revisoes.analisar_integridade([protocolo], agora=1200)
        codigos = {item["codigo"] for item in resultado["ocorrencias"]}
        self.assertIn("aprovacao_sem_revisor", codigos)
        self.assertIn("trilha_divergente", codigos)
        self.assertEqual(resultado["criticas"], 1)

    def test_detecta_duplicidade_e_recompensa_invalida(self):
        base = {"id": "dup", "tipo": "especial", "status": "pendente", "recompensa_xp": -5}
        resultado = revisoes.analisar_integridade([base, dict(base)], agora=1200)
        codigos = [item["codigo"] for item in resultado["ocorrencias"]]
        self.assertIn("id_duplicado", codigos)
        self.assertEqual(codigos.count("recompensa_invalida"), 2)

    def test_preserva_legados_sem_trilha_e_nao_altera_os_registros(self):
        legado = {"id": "old", "tipo": "missao", "status": "pendente"}
        original = dict(legado)
        resultado = revisoes.analisar_integridade([legado], guild_id=10, agora=1200)
        self.assertEqual(resultado["sem_trilha"], 1)
        self.assertEqual(legado, original)

    def test_ignora_tipos_fora_do_escopo_de_missoes(self):
        pvp = {"id": "pvp", "tipo": "pvp", "status": "invalido"}
        resultado = revisoes.analisar_integridade([pvp], agora=1200)
        self.assertEqual(resultado["protocolos_analisados"], 0)
        self.assertEqual(resultado["total_ocorrencias"], 0)


class TestTrilhaAuditoriaRevisoes(unittest.IsolatedAsyncioTestCase):
    async def test_criacao_registra_evento_inicial_sem_apagar_legado(self):
        with patch.object(revisoes, "carregar", new=AsyncMock(side_effect=[{}, {}])), \
             patch.object(revisoes, "salvar", new=AsyncMock()):
            registro = await revisoes.criar_pendencia(
                10, "missao", 20, "ref-1", "https://cdn.example/prova.png",
                "Missão de teste", recompensa_xp=100,
            )
        self.assertEqual(registro["status"], "pendente")
        self.assertEqual(registro["trilha_auditoria"][0]["evento"], "protocolo_criado")
        self.assertEqual(registro["trilha_auditoria"][0]["status_novo"], "pendente")


if __name__ == "__main__":
    unittest.main()
