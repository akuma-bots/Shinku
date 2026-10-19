import unittest
from unittest.mock import AsyncMock, patch

from utils import missoes


class TestIntegridadeMissoes(unittest.IsolatedAsyncioTestCase):
    async def test_rejeita_recompensa_negativa_sem_gravar(self):
        with patch.object(missoes, "carregar", new=AsyncMock(return_value={"guilds": {}})), patch.object(
            missoes, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "não pode ser negativa"):
                await missoes.criar(123, "missao", "Treino", "Descrição", -50)

        salvar.assert_not_awaited()

    async def test_rejeita_titulo_vazio(self):
        with patch.object(missoes, "carregar", new=AsyncMock(return_value={"guilds": {}})), patch.object(
            missoes, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "título"):
                await missoes.criar(123, "missao", "  ", "Descrição", 10)

        salvar.assert_not_awaited()

    async def test_missao_legada_com_recompensa_negativa_e_normalizada_para_zero(self):
        normalizada = missoes._normalizar_missao({
            "id": "legacy-1",
            "titulo": "Missão antiga",
            "recompensa_xp": -999,
        })

        self.assertEqual(normalizada["recompensa_xp"], 0)
        self.assertEqual(normalizada["pontos"], 0)

    async def test_estrutura_legada_corrompida_nao_quebra_listagem(self):
        dados = {
            "guilds": {
                "123": {
                    "missoes": {"inválido": True},
                    "submissoes": [None, "texto", {"id": "sub-1", "status": "pendente"}],
                }
            }
        }

        with patch.object(missoes, "carregar", new=AsyncMock(return_value=dados)):
            lista = await missoes.listar(123)
            submissoes = await missoes.listar_submissoes(123, status="pendente")

        self.assertEqual(lista, [])
        self.assertEqual([s["id"] for s in submissoes], ["sub-1"])

    async def test_criacao_valida_persiste_recompensa_nao_negativa(self):
        dados = {"guilds": {}}
        with patch.object(missoes, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            missoes, "salvar", new=AsyncMock()
        ) as salvar:
            criada = await missoes.criar(123, "missao", "Treino", "Descrição", 25)

        self.assertEqual(criada["recompensa_xp"], 25)
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
