import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.logs import Logs
from cogs.novidades import _enviar_dm_com_retry


class TestRegistroDeNotas(unittest.TestCase):
    def test_notas_tem_apenas_um_gatilho_de_execucao(self):
        from pathlib import Path
        import ast

        caminho = Path(__file__).resolve().parents[1] / "cogs" / "novidades.py"
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        classe = next(
            node for node in arvore.body
            if isinstance(node, ast.ClassDef) and node.name == "Novidades"
        )
        metodos = {
            node.name for node in classe.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("on_ready", metodos)
        self.assertIn("_retry_releases", metodos)


class TestSistemaDM(unittest.IsolatedAsyncioTestCase):
    async def test_dm_nao_repete_erro_http_ambiguo(self):
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

        self.assertEqual(resultado, "temporaria")
        membro.send.assert_awaited_once()

    async def test_dm_timeout_nao_repete_envio_ambiguo(self):
        membro = Mock()
        membro.id = 789
        membro.send = AsyncMock(side_effect=[asyncio.TimeoutError(), None])

        with patch("cogs.novidades.asyncio.sleep", new_callable=AsyncMock) as dormir:
            resultado = await _enviar_dm_com_retry(
                membro,
                embed=discord.Embed(title="Teste"),
            )

        self.assertEqual(resultado, "temporaria")
        membro.send.assert_awaited_once()
        dormir.assert_not_awaited()

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
    async def test_exclusao_bruta_usa_cache_quando_indice_ainda_nao_foi_criado(self):
        from datetime import datetime, timezone
        bot = Mock()
        cog = Logs(bot)
        autor = Mock(bot=False, id=321)
        mensagem = Mock(
            author=autor, id=987, created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
            content="apagada rapidamente", attachments=[], guild=Mock(id=1563995879981981817),
        )
        payload = Mock(guild_id=1563995879981981817, message_id=987, channel_id=654, cached_message=mensagem)
        with patch("cogs.logs.monitoramento_membros.buscar_mensagem", new_callable=AsyncMock, return_value=None), patch(
            "cogs.logs.monitoramento_membros.registrar_mensagem", new_callable=AsyncMock
        ) as registrar:
            await cog.on_raw_message_delete(payload)
        registrar.assert_awaited_once()
        self.assertEqual(registrar.await_args.args[1], 321)
        self.assertEqual(registrar.await_args.args[2]["conteudo"], "apagada rapidamente")
        self.assertEqual(registrar.await_args.args[2]["status"], "excluida")

    async def test_exclusao_bruta_atualiza_historico_mesmo_sem_cache(self):
        bot = Mock()
        cog = Logs(bot)
        payload = Mock(guild_id=1563995879981981817, message_id=987, channel_id=654)
        with patch("cogs.logs.monitoramento_membros.buscar_mensagem", new_callable=AsyncMock, return_value={
            "user_id": 321, "channel_id": 654, "timestamp": 1_800_000_000,
        }), patch("cogs.logs.monitoramento_membros.registrar_mensagem", new_callable=AsyncMock) as registrar:
            await cog.on_raw_message_delete(payload)
        registrar.assert_awaited_once()
        self.assertEqual(registrar.await_args.args[1], 321)
        self.assertEqual(registrar.await_args.args[2]["status"], "excluida")

    async def test_mensagem_comum_e_persistida_no_historico_individual(self):
        from datetime import datetime, timezone
        bot = Mock()
        cog = Logs(bot)
        message = Mock()
        message.guild = Mock(id=1563995879981981817)
        message.author = Mock(bot=False, id=321)
        message.channel = Mock(id=654)
        message.created_at = datetime(2026, 11, 3, tzinfo=timezone.utc)
        message.content = "mensagem de teste"
        message.id = 987
        message.jump_url = "https://discord.com/channels/1/654/987"
        message.attachments = []
        with patch("cogs.logs.monitoramento_membros.registrar_mensagem", new_callable=AsyncMock) as registrar:
            await cog.on_message(message)
        registrar.assert_awaited_once()
        registro = registrar.await_args.args[2]
        self.assertEqual(registro["conteudo"], "mensagem de teste")
        self.assertEqual(registro["status"], "enviada")
        self.assertEqual(registro["message_id"], "987")

    async def test_edicao_apenas_de_anexos_fica_registrada_privadamente(self):
        from datetime import datetime, timezone
        bot = Mock()
        cog = Logs(bot)
        autor = Mock(bot=False, id=123)
        canal = Mock(id=10)
        antes = Mock()
        antes.author = autor
        antes.guild = Mock(id=1563995879981981817)
        antes.channel = canal
        antes.content = "mesma mensagem"
        antes.id = 321
        antes.created_at = datetime(2026, 11, 3, tzinfo=timezone.utc)
        antes.attachments = [Mock(filename="antigo.png", url="https://example.com/antigo.png")]
        depois = Mock()
        depois.author = autor
        depois.guild = antes.guild
        depois.channel = canal
        depois.content = "mesma mensagem"
        depois.id = 321
        depois.created_at = antes.created_at
        depois.jump_url = "https://discord.com/channels/1/10/321"
        depois.attachments = [Mock(filename="novo.png", url="https://example.com/novo.png")]

        with patch("cogs.logs.monitoramento_membros.registrar_mensagem", new_callable=AsyncMock) as registrar:
            with patch.object(cog, "_enviar_log", new_callable=AsyncMock) as enviar:
                await cog.on_message_edit(antes, depois)

        registrar.assert_awaited_once()
        registro = registrar.await_args.args[2]
        self.assertEqual(registro["status"], "editada")
        self.assertEqual(registro["anexos"][0]["nome"], "novo.png")
        enviar.assert_not_awaited()

    async def test_exclusao_fica_no_historico_privado_sem_publicacao_no_forum(self):
        from datetime import datetime, timezone
        bot = Mock()
        cog = Logs(bot)
        autor = Mock(bot=False, id=321)
        autor.mention = "<@321>"
        canal = Mock(id=654)
        mensagem = Mock(
            author=autor,
            guild=Mock(id=1563995879981981817),
            channel=canal,
            id=987,
            created_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
            content="mensagem removida",
            jump_url="https://discord.com/channels/1/654/987",
            attachments=[],
        )
        with patch("cogs.logs.monitoramento_membros.registrar_mensagem", new_callable=AsyncMock) as registrar:
            with patch.object(cog, "_enviar_log", new_callable=AsyncMock) as enviar:
                await cog.on_message_delete(mensagem)

        registrar.assert_awaited_once()
        registro = registrar.await_args.args[2]
        self.assertEqual(registro["conteudo"], "mensagem removida")
        self.assertEqual(registro["status"], "excluida")
        enviar.assert_not_awaited()

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
