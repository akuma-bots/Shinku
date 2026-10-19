import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils import recordes


class TestIntegridadeRecordes(unittest.IsolatedAsyncioTestCase):
    async def test_rejeita_valor_nao_finito_ou_negativo(self):
        with patch.object(recordes, "carregar", new=AsyncMock(return_value={})), patch.object(
            recordes, "salvar", new=AsyncMock()
        ) as salvar:
            for valor in (-1, float("nan"), float("inf"), "inválido"):
                with self.assertRaises(ValueError):
                    await recordes.verificar_e_atualizar(123, "xp_total", 456, valor)

        salvar.assert_not_awaited()

    async def test_recorde_existente_maior_nao_e_substituido(self):
        dados = {"123": {"xp_total": {"user_id": 456, "valor": 100}}}
        with patch.object(recordes, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            recordes, "salvar", new=AsyncMock()
        ) as salvar:
            resultado = await recordes.verificar_e_atualizar(123, "xp_total", 789, 99)

        self.assertIsNone(resultado)
        salvar.assert_not_awaited()

    async def test_updates_concorrentes_preservam_o_maior_recorde(self):
        dados = {}
        with patch.object(recordes, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            recordes, "salvar", new=AsyncMock()
        ):
            await asyncio.gather(
                recordes.verificar_e_atualizar(123, "xp_total", 1, 10),
                recordes.verificar_e_atualizar(123, "xp_total", 2, 20),
                recordes.verificar_e_atualizar(123, "xp_total", 3, 15),
            )

        self.assertEqual(dados["123"]["xp_total"]["valor"], 20)

    async def test_listagem_ignora_registros_corrompidos(self):
        dados = {"123": ["inválido"]}
        with patch.object(recordes, "carregar", new=AsyncMock(return_value=dados)):
            resultado = await recordes.obter_todos(123)

        self.assertEqual(resultado, {})


if __name__ == "__main__":
    unittest.main()
