import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from cogs.missoes import Missoes
from utils import ranking_missoes_jogos


class TestRankingEmbedDesign(unittest.IsolatedAsyncioTestCase):
    async def test_ranking_usa_hierarquia_visual_compacta(self):
        guild = SimpleNamespace(id=1563995879981981817)
        cog = Missoes.__new__(Missoes)
        with (
            patch.object(
                ranking_missoes_jogos,
                "obter_ranking",
                new=AsyncMock(return_value=[(123, "Jogador", 385)]),
            ),
            patch.object(
                ranking_missoes_jogos,
                "obter_estatisticas_jogadores",
                new=AsyncMock(return_value={
                    "123": {
                        "vitorias": 1,
                        "empates": 0,
                        "derrotas": 0,
                        "xp": 385,
                        "kills": 2,
                        "deaths": 1,
                        "kdr": 2.0,
                        "mvps": 1,
                        "sequencia": 1,
                        "maior_sequencia": 3,
                        "patente": "Tenente",
                        "tempo_top": 180000,
                    }
                }),
            ),
        ):
            embed = await cog._montar_painel_ranking(guild, "shigaku")

        self.assertIn("RANKING SHIGAKU", embed.title)
        self.assertIn("JOGO SELECIONADO", embed.description)
        self.assertIn("🥇 <@123>", embed.description)
        self.assertIn("385 XP", embed.description)
        self.assertTrue(any("K/D" in field.value and "2/1" in field.value for field in embed.fields))
        self.assertTrue(any("Tenente" in field.value for field in embed.fields))
        self.assertIn("PÁGINA:shigaku", embed.footer.text)
        self.assertEqual(embed.color.value, 0x9F2035)

    async def test_ranking_vazio_mostra_mensagem_curta(self):
        guild = SimpleNamespace(id=1563995879981981817)
        cog = Missoes.__new__(Missoes)
        with patch.object(
            ranking_missoes_jogos,
            "obter_ranking",
            new=AsyncMock(return_value=[]),
        ):
            embed = await cog._montar_painel_ranking(guild, "shigaku")

        self.assertIn("Ainda não há jogadores classificados", embed.description)
        self.assertIn("Use os botões abaixo", embed.description)


if __name__ == "__main__":
    unittest.main()
