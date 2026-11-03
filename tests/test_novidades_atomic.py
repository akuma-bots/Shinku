import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cogs import novidades


class TestReservaNovidades(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.estado = {"guilds": {}}

        async def atualizar_json(_arquivo, padrao, transformador):
            atual = copy.deepcopy(self.estado if self.estado is not None else padrao)
            novo = transformador(atual)
            self.estado = copy.deepcopy(atual if novo is None else novo)
            return copy.deepcopy(self.estado)

        self.patch_storage = patch.object(novidades, "atualizar_json", side_effect=atualizar_json)
        self.patch_storage.start()
        self.addCleanup(self.patch_storage.stop)
        self.cog = novidades.Novidades(SimpleNamespace())

    async def test_destinatario_so_pode_ser_reservado_uma_vez(self):
        primeira = await self.cog._reservar_destinatario_release(10, "release-a", "123")
        segunda = await self.cog._reservar_destinatario_release(10, "release-a", "123")
        self.assertTrue(primeira)
        self.assertFalse(segunda)

    async def test_resultado_preserva_reserva_e_classifica_envio(self):
        await self.cog._reservar_destinatario_release(10, "release-a", "123")
        await self.cog._registrar_resultado_release(10, "release-a", "123", "enviada")
        registro = self.estado["guilds"]["10"]["release-a"]
        self.assertEqual(registro["dms_tentadas"], ["123"])
        self.assertEqual(registro["dms_enviadas"], ["123"])

    async def test_resultado_incerto_nao_e_reenviado(self):
        await self.cog._reservar_destinatario_release(10, "release-a", "123")
        await self.cog._registrar_resultado_release(10, "release-a", "123", "temporaria")
        self.assertFalse(await self.cog._reservar_destinatario_release(10, "release-a", "123"))
        self.assertEqual(
            self.estado["guilds"]["10"]["release-a"]["dms_resultado_incerto"],
            ["123"],
        )


if __name__ == "__main__":
    unittest.main()
