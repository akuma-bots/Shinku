import asyncio
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

    async def test_dm_repete_timeout_de_conexao(self):
        membro = Mock()
        membro.id = 789
        membro.send = AsyncMock(side_effect=[asyncio.TimeoutError(), None])

        with patch("cogs.novidades.asyncio.sleep", new_callable=AsyncMock) as dormir:
            resultado = await _enviar_dm_com_retry(
                membro,
                embed=discord.Embed(title="Teste"),
            )

        self.assertEqual(resultado, "enviada")
        self.assertEqual(membro.send.await_count, 2)
        dormir.assert_awaited_once()

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
    async def test_edicao_apenas_de_anexos_fica_registrada(self):
        bot = Mock()
        cog = Logs(bot)
        autor = Mock()
        autor.bot = False
        autor.id = 123
        autor.mention = "<@123>"
        canal_origem = Mock()
        canal_origem.id = 10
        canal_origem.mention = "<#10>"
        canal_logs = Mock()
        canal_logs.id = 20
        antes = Mock()
        antes.author = autor
        antes.guild = Mock()
        antes.channel = canal_origem
        antes.content = "mesma mensagem"
        antes.id = 321
        antes.attachments = [Mock(filename="antigo.png", url="https://example.com/antigo.png")]
        depois = Mock()
        depois.author = autor
        depois.guild = antes.guild
        depois.channel = canal_origem
        depois.content = "mesma mensagem"
        depois.id = 321
        depois.attachments = [Mock(filename="novo.png", url="https://example.com/novo.png")]

        with patch.object(cog, "_canal_logs", new_callable=AsyncMock, return_value=canal_logs):
            with patch.object(cog, "_enviar_log", new_callable=AsyncMock, return_value=True) as enviar:
                await cog.on_message_edit(antes, depois)

        enviar.assert_awaited_once()
        embed = enviar.await_args.args[1]
        nomes = [campo.name for campo in embed.fields]
        self.assertIn("Anexos anteriores", nomes)
        self.assertIn("Anexos atuais", nomes)

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
