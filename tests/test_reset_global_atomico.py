import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import perfis, ranking_missoes_jogos, storage


class TestResetGlobalAtomico(unittest.IsolatedAsyncioTestCase):
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

    async def test_reset_preserva_catalogo_identidades_e_campos_extras(self):
        await storage.salvar("perfis.json", {
            "10": {
                "20": {
                    "xp": 900, "pontos_pve": 40, "vitorias": 7,
                    "medalhas": ["Lenda"], "patente": "Elite",
                    "recompensas_missoes_aplicadas": ["REV-1"],
                    "custom": "preservar",
                }
            }
        })
        await storage.salvar("competitivo.json", {
            "catalogo": [{"id": "cat-1"}],
            "perfis": {
                "20": {
                    "discordId": "20", "nome": "Membro", "pontos": 800,
                    "pontos_temporada": 300, "xp": 900, "vitorias": 7,
                    "tempo_top_global_segundos": 500,
                }
            },
            "temporada_global": {"numero": 4, "historico": [{"numero": 3}]},
        })

        resultado = await perfis.resetar_perfis_globais(
            agora=5000, operation_id="reset-op-1"
        )
        locais = await storage.carregar("perfis.json", {})
        competitivos = await storage.carregar("competitivo.json", {})
        perfil_local = locais["10"]["20"]
        perfil_competitivo = competitivos["perfis"]["20"]

        self.assertEqual(resultado["quantidade_local"], 1)
        self.assertEqual(resultado["quantidade_global"], 1)
        self.assertEqual(perfil_local["xp"], 0)
        self.assertEqual(perfil_local["pontos_pve"], 0)
        self.assertEqual(perfil_local["medalhas"], [])
        self.assertEqual(perfil_local["custom"], "preservar")
        self.assertEqual(perfil_competitivo["pontos"], 0)
        self.assertEqual(perfil_competitivo["xp"], 0)
        self.assertEqual(competitivos["catalogo"], [{"id": "cat-1"}])
        self.assertEqual(competitivos["temporada_global"]["historico"], [])

    async def test_mesma_operacao_nao_apaga_progresso_gerado_depois(self):
        await storage.salvar("perfis.json", {"10": {"20": {"xp": 100}}})
        await perfis.resetar_perfis_globais(agora=5000, operation_id="reset-op-2")
        await perfis.atualizar_perfil(
            10, 20, lambda perfil: {**perfil, "xp": perfil["xp"] + 25}
        )
        repetido = await perfis.resetar_perfis_globais(
            agora=5100, operation_id="reset-op-2"
        )
        perfil = await perfis.get_perfil(10, 20)
        self.assertEqual(repetido["quantidade_local"], 0)
        self.assertEqual(perfil["xp"], 25)

    async def test_reset_de_ranking_por_jogo_preserva_referencia_do_painel(self):
        await storage.salvar(ranking_missoes_jogos.ARQUIVO, {
            "99": {
                "paineis": {"ranking": 777},
                "jogos": {
                    slug: {
                        "pontuacao": {"20": {"pontos": 500}},
                        "eventos_aplicados": ["evento-antigo"],
                    }
                    for slug in ranking_missoes_jogos.JOGOS
                },
            }
        })
        quantidade = await ranking_missoes_jogos.resetar_pontuacoes_jogos(
            99, operation_id="reset-jogos-1"
        )
        dados = await storage.carregar(ranking_missoes_jogos.ARQUIVO, {})
        registro = dados["99"]
        self.assertEqual(quantidade, len(ranking_missoes_jogos.JOGOS))
        self.assertEqual(registro["paineis"]["ranking"], 777)
        for jogo in ranking_missoes_jogos.JOGOS:
            self.assertEqual(registro["jogos"][jogo]["pontuacao"], {})
            self.assertEqual(registro["jogos"][jogo]["eventos_aplicados"], [])
            self.assertEqual(registro["jogos"][jogo]["ranking_message_id"], 777)

        registro["jogos"][next(iter(ranking_missoes_jogos.JOGOS))]["pontuacao"]["30"] = {"pontos": 99}
        await storage.salvar(ranking_missoes_jogos.ARQUIVO, dados)
        repetido = await ranking_missoes_jogos.resetar_pontuacoes_jogos(
            99, operation_id="reset-jogos-1"
        )
        atual = await storage.carregar(ranking_missoes_jogos.ARQUIVO, {})
        self.assertEqual(repetido, 0)
        self.assertEqual(
            atual["99"]["jogos"][next(iter(ranking_missoes_jogos.JOGOS))]["pontuacao"]["30"]["pontos"],
            99,
        )


if __name__ == "__main__":
    unittest.main()
