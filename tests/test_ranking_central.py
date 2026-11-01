import unittest
from types import SimpleNamespace

from cogs.ranking_geral import CentralRankingGeralView, RankingGeral


class TestRankingCentral(unittest.TestCase):
    def test_funcoes_de_canal_e_temporada_nao_sao_comandos_independentes(self):
        nomes = {
            comando.name
            for comando in getattr(RankingGeral, "__cog_app_commands__", [])
        }
        self.assertNotIn("ranking-canal", nomes)
        self.assertNotIn("temporada-reiniciar", nomes)
        # O comando público restante continua servindo como acesso informativo.
        self.assertIn("ranking-geral", nomes)

    def test_central_concentra_seletor_e_acoes_em_componentes(self):
        central = CentralRankingGeralView(
            cog=None,
            guild=SimpleNamespace(id=123, name="NÊMESIS"),
            owner_id=456,
        )
        botoes = [
            item.label for item in central.children
            if getattr(item, "label", None)
        ]
        self.assertIn("Reiniciar temporada", botoes)
        self.assertIn("Atualizar ranking", botoes)
        self.assertIn("Fechar central", botoes)
        self.assertTrue(any(item.__class__.__name__ == "SeletorCanalRanking" for item in central.children))


if __name__ == "__main__":
    unittest.main()
