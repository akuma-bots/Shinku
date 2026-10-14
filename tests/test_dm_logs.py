import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.logs import Logs
from cogs.novidades import _enviar_dm_com_retry


class TestSistemaDM(unittest.IsolatedAsyncioTestCase):
    async def test_dm_repete_falha_transitoria_e_entrega(self):
        membro = Mock()
        membro.id = 123
        membro.send = AsyncMock(side_effect=[
            discord.HTTPException(
                response=Mock(status=500, reason="Internal Server Error"),
                message="temporary",
            ),
            None,
        ])

        with patch("cogs.novidades.asyncio.sleep", new_callable=AsyncMock):
            resultado = await _enviar_dm_com_retry(
                membro,
                embed=discord.Embed(title="Teste"),
            )

        self.assertEqual(resultado, "enviada")
        self.assertEqual(membro.send.await_count, 2)

    async def test_dm_bloqueada_nao_faz_retry(self):
        membro = Mock()
        membro.id = 456
        membro.send = AsyncMock(side_effect=discord.Forbidden(
            response=Mock(status=403, reason="Forbidden"),
            message="DM disabled",
        ))

        with patch("cogs.novidades.asyncio.sleep", new_callable=AsyncMock) as dormir:
            resultado = await _enviar_dm_com_retry(
                membro,
                embed=discord.Embed(title="Teste"),
            )

        self.assertEqual(resultado, "permanente")
        membro.send.assert_awaited_once()
        dormir.assert_not_awaited()


class TestSistemaLogs(unittest.IsolatedAsyncioTestCase):
    async def test_falha_de_permissao_no_canal_nao_escapa_do_listener(self):
        bot = Mock()
        cog = Logs(bot)
        canal = Mock()
        canal.id = 999
        canal.send = AsyncMock(side_effect=discord.Forbidden(
            response=Mock(status=403, reason="Forbidden"),
            message="Missing permissions",
        ))

        resultado = await cog._enviar_log(canal, discord.Embed(title="Teste"))

        self.assertFalse(resultado)
        canal.send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
