import unittest
from unittest.mock import AsyncMock, patch

from utils import ranking_missoes_jogos


class TestRankingMissoesJogos(unittest.IsolatedAsyncioTestCase):
    async def test_registrar_pontos_normaliza_ledger_textual_e_pontuacao_invalida(self):
        dados = {
            "1563995879981981817": {
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
                guild_id=1563995879981981817,
                jogo="shigaku",
                user_id=123,
                nome="Membro",
                pontos=5,
                evento_id="evento-novo",
            )

        self.assertTrue(aplicado)
        perfil = dados["1563995879981981817"]["jogos"]["shigaku"]["pontuacao"]["123"]
        self.assertEqual(perfil["pontos"], 5)
        self.assertEqual(
            dados["1563995879981981817"]["jogos"]["shigaku"]["eventos_aplicados"],
            ["evento-antigo", "evento-novo"],
        )
        salvar.assert_awaited_once()

    async def test_evento_ja_aplicado_nao_duplica_pontos(self):
        dados = {
            "1563995879981981817": {
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
                guild_id=1563995879981981817,
                jogo="shigaku",
                user_id=123,
                nome="Membro",
                pontos=5,
                evento_id="missao:42",
            )

        self.assertFalse(aplicado)
        self.assertEqual(dados["1563995879981981817"]["jogos"]["shigaku"]["pontuacao"]["123"]["pontos"], 10)
        salvar.assert_not_awaited()

    async def test_ranking_ignora_perfis_com_pontuacao_invalida(self):
        dados = {
            "1563995879981981817": {
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
            ranking = await ranking_missoes_jogos.obter_ranking(1563995879981981817, "shigaku")

        self.assertEqual(ranking, [("456", "Membro B", 20)])

    async def test_ranking_geral_soma_pontos_de_todos_os_jogos_e_do_novo_ledger(self):
        dados = {
            "1563995879981981817": {
                "jogos": {
                    "shigaku": {"pontuacao": {"123": {"nome": "Jogador", "pontos": 100}}},
                    "gakuran": {"pontuacao": {"123": {"nome": "Jogador", "pontos": 75}, "456": {"nome": "Outro", "pontos": 50}}},
                },
                "ranking_geral": {"pontuacao": {"123": {"nome": "Jogador", "pontos": 25}, "789": {"nome": "Novo", "pontos": 40}}},
            }
        }
        with patch.object(ranking_missoes_jogos, "carregar", new=AsyncMock(return_value=dados)):
            ranking = await ranking_missoes_jogos.obter_ranking_geral(1563995879981981817)
        self.assertEqual(ranking, [("123", "Jogador", 200), ("456", "Outro", 50), ("789", "Novo", 40)])

    async def test_registrar_pontos_gerais_aceita_missao_sem_jogo_e_e_idempotente(self):
        dados = {"1563995879981981817": {}}
        with patch.object(ranking_missoes_jogos, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            ranking_missoes_jogos, "salvar", new=AsyncMock()
        ) as salvar:
            primeira = await ranking_missoes_jogos.registrar_pontos_gerais(
                1563995879981981817, 123, "Jogador", 35, "missao:abc:123"
            )
            segunda = await ranking_missoes_jogos.registrar_pontos_gerais(
                1563995879981981817, 123, "Jogador", 35, "missao:abc:123"
            )
        self.assertTrue(primeira)
        self.assertFalse(segunda)
        perfil = dados["1563995879981981817"]["ranking_geral"]["pontuacao"]["123"]
        self.assertEqual(perfil["pontos"], 35)
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
