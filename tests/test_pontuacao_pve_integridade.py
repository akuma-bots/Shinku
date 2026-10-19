import unittest
from unittest.mock import AsyncMock, patch

from utils import pontuacao_pve


class TestIntegridadePontuacaoPve(unittest.IsolatedAsyncioTestCase):
    async def test_rejeita_pontos_negativos(self):
        with patch.object(pontuacao_pve, "get_perfil", new=AsyncMock(return_value={"pontos_pve": 10})), patch.object(
            pontuacao_pve, "_salvar_perfil", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "não pode ser negativa"):
                await pontuacao_pve.adicionar_pontos(123, 456, -5)

        salvar.assert_not_awaited()

    async def test_adiciona_pontos_ao_total_normalizado(self):
        perfil = {"pontos_pve": "inválido", "xp": 100}
        with patch.object(pontuacao_pve, "get_perfil", new=AsyncMock(return_value=perfil)), patch.object(
            pontuacao_pve, "_salvar_perfil", new=AsyncMock()
        ) as salvar:
            total = await pontuacao_pve.adicionar_pontos(123, 456, 15)

        self.assertEqual(total, 15)
        self.assertEqual(perfil["xp"], 100)
        salvar.assert_awaited_once()

    async def test_ranking_ignora_perfis_invalidos_e_ordena_empates(self):
        dados = {
            "123": {
                "a": {"pontos_pve": 20},
                "b": {"pontos_pve": "inválido"},
                "c": {"pontos_pve": 20},
                "d": None,
                "e": {"pontos_pve": -5},
            }
        }
        with patch.object(pontuacao_pve, "carregar", new=AsyncMock(return_value=dados)):
            ranking = await pontuacao_pve.obter_ranking(123, 10)

        self.assertEqual(ranking, [("a", 20), ("c", 20)])

    async def test_storage_raiz_invalido_retorna_ranking_vazio(self):
        with patch.object(pontuacao_pve, "carregar", new=AsyncMock(return_value=[])):
            ranking = await pontuacao_pve.obter_ranking(123)

        self.assertEqual(ranking, [])


if __name__ == "__main__":
    unittest.main()
