import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from cogs import automod


class TestPersistenciaBanTemporario(unittest.IsolatedAsyncioTestCase):
    def criar_cog(self):
        cog = object.__new__(automod.AutoMod)
        cog._banimentos_lock = asyncio.Lock()
        cog.bot = None
        return cog

    async def test_falha_ao_carregar_nao_finge_registro_persistido(self):
        cog = self.criar_cog()
        with patch.object(automod, "carregar", new=AsyncMock(side_effect=RuntimeError("storage indisponível"))), patch.object(
            automod, "salvar", new=AsyncMock()
        ) as salvar:
            resultado = await cog.registrar_banimento_temporario(123, 456, 3600)

        self.assertFalse(resultado)
        salvar.assert_not_awaited()

    async def test_falha_ao_salvar_retorna_false(self):
        cog = self.criar_cog()
        with patch.object(automod, "carregar", new=AsyncMock(return_value={})), patch.object(
            automod, "salvar", new=AsyncMock(side_effect=RuntimeError("disco indisponível"))
        ):
            resultado = await cog.registrar_banimento_temporario(123, 456, 3600)

        self.assertFalse(resultado)

    async def test_registro_salvo_retorna_true(self):
        cog = self.criar_cog()
        dados = {}
        with patch.object(automod, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            automod, "salvar", new=AsyncMock()
        ) as salvar:
            resultado = await cog.registrar_banimento_temporario(123, 456, 3600)

        self.assertTrue(resultado)
        salvar.assert_awaited_once()
        self.assertIn("123:456", dados)
        self.assertGreater(dados["123:456"]["expira_em"], 0)


if __name__ == "__main__":
    unittest.main()
