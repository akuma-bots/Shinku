import unittest
from unittest.mock import AsyncMock, patch

from utils import ranking_missoes_jogos


class TestRankingMissoesJogos(unittest.IsolatedAsyncioTestCase):
    async def test_registrar_pontos_normaliza_ledger_textual_e_pontuacao_invalida(self):
        dados = {
            "1543381737961160910": {
                "jogos": {
                    "shigaku": {
                        "eventos_aplicados": "evento-antigo",
                        "pontuacao": {"123": {"nome": "Membro", "pontos": "inválido"}},
                    }
                }
            }
        }

        with patch.object(ranking_missoes_jogos, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            ranking_missoes_jogos, "salvar", new=AsyncMock()
        ) as salvar:
            aplicado = await ranking_missoes_jogos.registrar_pontos(
                guild_id=1543381737961160910,
                jogo="shigaku",
                user_id=123,
                nome="Membro",
                pontos=5,
                evento_id="evento-novo",
            )

        self.assertTrue(aplicado)
        perfil = dados["1543381737961160910"]["jogos"]["shigaku"]["pontuacao"]["123"]
        self.assertEqual(perfil["pontos"], 5)
        self.assertEqual(
            dados["1543381737961160910"]["jogos"]["shigaku"]["eventos_aplicados"],
            ["evento-antigo", "evento-novo"],
        )
        salvar.assert_awaited_once()

    async def test_evento_ja_aplicado_nao_duplica_pontos(self):
        dados = {
            "1543381737961160910": {
                "jogos": {
                    "shigaku": {
                        "eventos_aplicados": ["missao:42"],
                        "pontuacao": {"123": {"nome": "Membro", "pontos": 10}},
                    }
                }
            }
        }

        with patch.object(ranking_missoes_jogos, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            ranking_missoes_jogos, "salvar", new=AsyncMock()
        ) as salvar:
            aplicado = await ranking_missoes_jogos.registrar_pontos(
                guild_id=1543381737961160910,
                jogo="shigaku",
                user_id=123,
                nome="Membro",
                pontos=5,
                evento_id="missao:42",
            )

        self.assertFalse(aplicado)
        self.assertEqual(dados["1543381737961160910"]["jogos"]["shigaku"]["pontuacao"]["123"]["pontos"], 10)
        salvar.assert_not_awaited()

    async def test_ranking_ignora_perfis_com_pontuacao_invalida(self):
        dados = {
            "1543381737961160910": {
                "jogos": {
                    "shigaku": {
                        "pontuacao": {
                            "123": {"nome": "Membro A", "pontos": "inválido"},
                            "456": {"nome": "Membro B", "pontos": 20},
                            "789": {"nome": "Membro C", "pontos": -5},
                        }
                    }
                }
            }
        }

        with patch.object(ranking_missoes_jogos, "carregar", new=AsyncMock(return_value=dados)):
            ranking = await ranking_missoes_jogos.obter_ranking(1543381737961160910, "shigaku")

        self.assertEqual(ranking, [("456", "Membro B", 20)])


if __name__ == "__main__":
    unittest.main()
