import unittest
from unittest.mock import AsyncMock, patch

from utils import temporadas


class TestIntegridadeTemporadas(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_retorna_estado_padrao(self):
        with patch.object(temporadas, "_tudo", new=AsyncMock(return_value=[])):
            estado = await temporadas.get_estado(123)

        self.assertEqual(estado["numero_atual"], 1)
        self.assertEqual(estado["duracao_dias"], 30)
        self.assertEqual(estado["historico"], [])

    async def test_estado_legado_normaliza_duracao_e_bonus(self):
        with patch.object(temporadas, "_tudo", new=AsyncMock(return_value={
            "123": {
                "numero_atual": -4,
                "duracao_dias": 0,
                "bonus_ouro": -100,
                "baseline": None,
                "historico": "inválido",
            }
        })):
            estado = await temporadas.get_estado(123)

        self.assertEqual(estado["numero_atual"], 1)
        self.assertEqual(estado["duracao_dias"], 1)
        self.assertGreaterEqual(estado["bonus_ouro"], 0)
        self.assertEqual(estado["baseline"], {})
        self.assertEqual(estado["historico"], [])

    async def test_rejeita_duracao_fora_da_faixa(self):
        with patch.object(temporadas, "_tudo", new=AsyncMock(return_value={})), patch.object(
            temporadas, "_salvar_estado", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "1 e 365"):
                await temporadas.configurar(123, duracao_dias=0)

        salvar.assert_not_awaited()

    async def test_rejeita_bonus_negativo(self):
        with patch.object(temporadas, "_tudo", new=AsyncMock(return_value={})), patch.object(
            temporadas, "_salvar_estado", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "não podem ser negativos"):
                await temporadas.configurar(123, bonus_ouro=-1)

        salvar.assert_not_awaited()

    async def test_calculo_de_pontuacao_ignora_valores_invalidos(self):
        self.assertEqual(
            temporadas._pontuacao(
                {"xp": "inválido", "vitorias": -2, "mvps": 3},
                {"xp": 1, "vitoria": 10, "mvp": 20},
            ),
            60,
        )


if __name__ == "__main__":
    unittest.main()
