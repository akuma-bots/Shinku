import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord

from utils import auditoria


class TestResilienciaAuditoria(unittest.IsolatedAsyncioTestCase):
    async def test_publica_embed_sem_mencoes(self):
        canal = Mock()
        canal.send = AsyncMock()
        guild = Mock()
        guild.id = 123
        guild.get_channel.return_value = canal

        with patch.object(auditoria, "get_config", new=AsyncMock(return_value={"canal_auditoria_id": 456})):
            resultado = await auditoria.registrar(guild, "Teste", "Detalhes <@999>")

        self.assertTrue(resultado)
        canal.send.assert_awaited_once()
        kwargs = canal.send.await_args.kwargs
        self.assertIsInstance(kwargs["embed"], discord.Embed)
        self.assertIsNotNone(kwargs["embed"].timestamp)
        self.assertIsNotNone(kwargs["allowed_mentions"])

    async def test_canal_indisponivel_nao_derruba_fluxo(self):
        guild = Mock()
        guild.id = 123
        guild.get_channel.return_value = None
        guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(Mock(), "not found"))

        with patch.object(auditoria, "get_config", new=AsyncMock(return_value={"canal_auditoria_id": 456})):
            resultado = await auditoria.registrar(guild, "Teste", "Detalhes")

        self.assertFalse(resultado)

    async def test_auditoria_desativada_retorna_false(self):
        guild = Mock()
        guild.id = 123

        with patch.object(auditoria, "get_config", new=AsyncMock(return_value={"canal_auditoria_id": None})):
            resultado = await auditoria.registrar(guild, "Teste", "Detalhes")

        self.assertFalse(resultado)


if __name__ == "__main__":
    unittest.main()
