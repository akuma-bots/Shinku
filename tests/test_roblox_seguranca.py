import unittest
from unittest.mock import AsyncMock, Mock, patch

import aiohttp

from cogs import roblox


class TestSegurancaRoblox(unittest.IsolatedAsyncioTestCase):
    async def test_config_grupo_corrompida_usa_padrao_seguro(self):
        with patch.object(roblox, "carregar", new=AsyncMock(return_value=[])):
            config = await roblox._config_grupo(123)

        self.assertIsNone(config["grupo_id"])
        self.assertEqual(config["mapeamentos"], {})

    async def test_config_filtra_mapeamentos_invalidos(self):
        dados = {
            "123": {
                "grupo_id": "456",
                "mapeamentos": {
                    "Oficial": "789",
                    "Inválido": "texto",
                    "": 111,
                },
            }
        }
        with patch.object(roblox, "carregar", new=AsyncMock(return_value=dados)):
            config = await roblox._config_grupo(123)

        self.assertEqual(config["grupo_id"], 456)
        self.assertEqual(config["mapeamentos"], {"Oficial": 789})

    async def test_falha_da_api_nao_remove_cargos_de_rank(self):
        cargo = Mock()
        cargo.id = 789
        membro = Mock()
        membro.roles = [cargo]
        membro.remove_roles = AsyncMock()
        membro.add_roles = AsyncMock()
        guild = Mock()
        guild.id = 123

        with patch.object(roblox, "_config_grupo", new=AsyncMock(return_value={
            "grupo_id": 456,
            "mapeamentos": {"Oficial": 789},
        })), patch.object(
            roblox, "_buscar_rank_no_grupo", new=AsyncMock(side_effect=aiohttp.ClientError("429"))
        ):
            resultado = await roblox.sincronizar_cargo_membro(guild, membro, 111)

        self.assertIn("Erro ao consultar", resultado)
        membro.remove_roles.assert_not_awaited()
        membro.add_roles.assert_not_awaited()

    async def test_grupos_legados_corrompidos_nao_quebram_lookup(self):
        with patch.object(roblox, "_buscar_grupos_roblox", new=AsyncMock(return_value=[
            None,
            {},
            {"group": {"id": "inválido"}, "role": None},
        ])):
            resultado = await roblox._buscar_rank_no_grupo(111, 456)

        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
