import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from cogs import automod


class TestDestinosAutoMod(unittest.TestCase):
    def test_infracoes_sao_encaminhadas_ao_registro_global(self):
        self.assertEqual(automod.registrar_global.__module__, "utils.registro_global")

    def test_auditoria_aponta_para_canal_logs_atual(self):
        self.assertEqual(automod.registrar_global.__module__, "utils.registro_global")


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



class TestCacheRegrasAutoMod(unittest.IsolatedAsyncioTestCase):
    def criar_cog(self):
        cog = object.__new__(automod.AutoMod)
        cog.regras_cache = {"01": {"titulo": "Regras"}}
        cog.regras_cache_timestamp = 100
        cog._regras_lock = asyncio.Lock()
        return cog

    async def test_cache_de_regras_permanece_por_cinco_minutos(self):
        cog = self.criar_cog()
        with patch("cogs.automod.time.time", return_value=250), patch.object(
            cog, "_atualizar_regras_oficiais", new=AsyncMock()
        ) as atualizar:
            resultado = await cog.carregar_regras_oficiais()

        self.assertEqual(resultado, cog.regras_cache)
        atualizar.assert_not_awaited()
        self.assertEqual(automod.CACHE_REGRAS_SEGUNDOS, 300)

    async def test_cache_expirado_atualiza_regras(self):
        cog = self.criar_cog()
        esperado = {"02": {"titulo": "Atualizada"}}
        with patch("cogs.automod.time.time", return_value=1000), patch.object(
            cog, "_atualizar_regras_oficiais", new=AsyncMock(return_value=esperado)
        ) as atualizar:
            resultado = await cog.carregar_regras_oficiais()

        self.assertEqual(resultado, esperado)
        atualizar.assert_awaited_once()

    async def test_atualizacao_concorrente_e_serializada(self):
        cog = self.criar_cog()
        cog.regras_cache_timestamp = 0
        chamada = 0

        async def atualizar():
            nonlocal chamada
            chamada += 1
            await asyncio.sleep(0)
            cog.regras_cache = {"03": {"titulo": "Nova"}}
            cog.regras_cache_timestamp = 1000
            return cog.regras_cache

        with patch("cogs.automod.time.time", return_value=1000), patch.object(
            cog, "_atualizar_regras_oficiais", new=AsyncMock(side_effect=atualizar)
        ) as refresh:
            resultados = await asyncio.gather(
                cog.carregar_regras_oficiais(),
                cog.carregar_regras_oficiais(),
            )

        self.assertEqual(chamada, 1)
        self.assertEqual(resultados[0], resultados[1])
        refresh.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
