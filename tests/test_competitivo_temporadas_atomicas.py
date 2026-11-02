import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import competitivo_sync, storage


class TestCompetitivoTemporadasAtomicas(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.patchers = [
            patch.object(storage, "DATA_DIR", Path(self.tempdir.name)),
            patch.object(storage, "USANDO_UPSTASH", False),
            patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", False),
        ]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)

    async def test_encerramento_automatico_preserva_historico_e_pontos_permanentes(self):
        await storage.salvar("competitivo.json", {
            "catalogo": [],
            "perfis": {
                "10": {
                    "discordId": "10", "nome": "Campeão",
                    "pontos": 900, "pontos_temporada": 120,
                    "vitorias": 8, "xp": 500, "tempo_top_global_segundos": 240,
                }
            },
            "temporada_global": {
                "numero": 3, "inicio_timestamp": 1000,
                "duracao_dias": 30, "historico": [],
            },
        })
        dados = await competitivo_sync.atualizar_temporada_global(1000 + 30 * 86400)
        estado = dados["temporada_global"]
        perfil = dados["perfis"]["10"]
        self.assertEqual(estado["numero"], 4)
        self.assertEqual(estado["historico"][0]["top"][0]["discordId"], "10")\n        self.assertEqual(estado["historico"][0]["top"][0]["xp_temporada"], 200)
        self.assertEqual(perfil["pontos"], 900)
        self.assertEqual(perfil["pontos_temporada"], 0)\n        self.assertEqual(perfil["xp_base_temporada"], 500)\n        self.assertEqual(perfil["xp_temporada"], 0)
        self.assertEqual(perfil["tempo_top_global_segundos"], 240)

    async def test_registro_top10_acumula_tempo_sem_gravacoes_perdidas(self):
        await storage.salvar("competitivo.json", {
            "catalogo": [],
            "perfis": {
                str(uid): {
                    "discordId": str(uid), "pontos": 100 - uid,
                    "pontos_temporada": 100 - uid, "xp": 100 - uid,\n                    "xp_base_temporada": 0, "xp_temporada": 100 - uid, "vitorias": 0,
                    "tempo_top_global_segundos": 0, "em_top_global": False,
                    "ultima_verificacao_top_global": 1000,
                }
                for uid in range(1, 13)
            },
            "temporada_global": {
                "numero": 1, "inicio_timestamp": 1000,
                "duracao_dias": 30, "historico": [],
            },
        })
        await competitivo_sync.registrar_tempo_top_global(1000, limite=10)
        dados = await competitivo_sync.registrar_tempo_top_global(1060, limite=10)
        self.assertEqual(dados["perfis"]["1"]["tempo_top_global_segundos"], 60)
        self.assertFalse(dados["perfis"]["12"]["em_top_global"])

    async def test_confirmacao_antiga_nao_reinicia_temporada_seguinte(self):
        await storage.salvar("competitivo.json", {
            "catalogo": [],
            "perfis": {"10": {"discordId": "10", "pontos": 400, "pontos_temporada": 200, "xp": 450, "xp_base_temporada": 250, "xp_temporada": 200}},
            "temporada_global": {
                "numero": 5, "inicio_timestamp": 1000,
                "duracao_dias": 30, "historico": [],
            },
        })
        dados = await competitivo_sync.reiniciar_temporada_global(
            agora=2000, numero_esperado=4
        )
        self.assertEqual(dados["temporada_global"]["numero"], 5)
        self.assertEqual(dados["temporada_global"]["historico"], [])

        dados = await competitivo_sync.reiniciar_temporada_global(
            agora=2000, numero_esperado=5
        )
        self.assertEqual(dados["temporada_global"]["numero"], 6)
        self.assertEqual(len(dados["temporada_global"]["historico"]), 1)
        self.assertEqual(dados["perfis"]["10"]["pontos"], 400)
        self.assertEqual(dados["perfis"]["10"]["pontos_temporada"], 0)\n        self.assertEqual(dados["perfis"]["10"]["xp_base_temporada"], 450)\n        self.assertEqual(dados["perfis"]["10"]["xp_temporada"], 0)


if __name__ == "__main__":
    unittest.main()
