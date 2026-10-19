import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils import punicoes


class TestIntegridadePunicoes(unittest.IsolatedAsyncioTestCase):
    async def test_storage_corrompido_nao_quebra_historico(self):
        with patch.object(punicoes, "carregar", new=AsyncMock(return_value=[])):
            self.assertEqual(await punicoes.historico_punicoes(123), [])
            self.assertEqual(await punicoes.obter_todas_punicoes(123), [])

    async def test_historico_ignora_registros_invalidos_e_normaliza_ids(self):
        dados = {
            "123": [
                None,
                "texto",
                {"id": "a", "membro_id": "456", "tipo": "warn", "timestamp": "2"},
                {"id": "b", "membro_id": 456, "tipo": "ban", "timestamp": "inválido"},
                {"id": "c", "membro_id": 789, "tipo": "kick", "timestamp": 3},
            ]
        }
        with patch.object(punicoes, "carregar", new=AsyncMock(return_value=dados)):
            resultado = await punicoes.historico_punicoes(123, membro_id=456)

        self.assertEqual({item["id"] for item in resultado}, {"a", "b"})

    async def test_registro_punitivo_preserva_eventos_concorrentes(self):
        dados = {}
        with patch.object(punicoes, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            punicoes, "salvar", new=AsyncMock()
        ) as salvar:
            await asyncio.gather(
                punicoes.registrar_punicao(123, 456, "warn", "Motivo A", 1),
                punicoes.registrar_punicao(123, 789, "kick", "Motivo B", 2),
            )

        self.assertEqual(len(dados["123"]), 2)
        salvar.assert_awaited()

    async def test_nao_permite_tipo_vazio(self):
        with patch.object(punicoes, "carregar", new=AsyncMock(return_value={})), patch.object(
            punicoes, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "tipo"):
                await punicoes.registrar_punicao(123, 456, "", "Motivo")

        salvar.assert_not_awaited()

    async def test_limite_de_historico_e_controlado(self):
        dados = {"123": [{"id": str(i), "membro_id": 456, "timestamp": i} for i in range(20)]}
        with patch.object(punicoes, "carregar", new=AsyncMock(return_value=dados)):
            resultado = await punicoes.historico_punicoes(123, limite=10000)

        self.assertEqual(len(resultado), 20)
        self.assertEqual(resultado[0]["id"], "19")


if __name__ == "__main__":
    unittest.main()
