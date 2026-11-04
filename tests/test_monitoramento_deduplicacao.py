import unittest
from unittest.mock import AsyncMock, Mock, patch

from cogs.logs import Logs
from utils import monitoramento_membros as monitor


GUILD_ID = 1563995879981981817


class TestIndiceDeMensagens(unittest.IsolatedAsyncioTestCase):
    async def test_status_final_da_mensagem_fica_no_indice_e_nao_duplica_registro(self):
        estado = {}

        async def atualizar(nome, padrao, transformador):
            atual = estado.get(nome, padrao)
            estado[nome] = transformador(atual)
            return estado[nome]

        with (
            patch.object(monitor, "atualizar_json", new=AsyncMock(side_effect=atualizar)),
            patch.object(monitor, "definir_expiracao", new=AsyncMock()),
            patch.object(monitor, "salvar_com_expiracao", new=AsyncMock()) as salvar_indice,
        ):
            await monitor.registrar_mensagem(GUILD_ID, 42, {
                "message_id": "9001", "canal_id": 77, "timestamp": 1_800_000_000,
                "conteudo": "original", "status": "enviada",
            })
            await monitor.registrar_mensagem(GUILD_ID, 42, {
                "message_id": "9001", "canal_id": 77, "timestamp": 1_800_000_000,
                "conteudo": "editada", "status": "editada",
            })
            await monitor.registrar_mensagem(GUILD_ID, 42, {
                "message_id": "9001", "canal_id": 77, "timestamp": 1_800_000_000,
                "conteudo": "editada", "status": "excluida", "excluida_em": 1_800_000_100,
            })
            # Segunda entrega do evento raw/cache: não deve criar outra linha
            # nem apagar o conteúdo que já estava arquivado.
            await monitor.registrar_mensagem(GUILD_ID, 42, {
                "message_id": "9001", "canal_id": 77, "timestamp": 1_800_000_000,
                "status": "excluida", "excluida_em": 1_800_000_101,
            })

        documento = estado[monitor._arquivo(GUILD_ID, 42)]
        self.assertEqual(len(documento["mensagens"]), 1)
        mensagem = documento["mensagens"][0]
        self.assertEqual(mensagem["conteudo"], "editada")
        self.assertEqual(mensagem["status"], "excluida")
        self.assertEqual(mensagem["revisoes"][0]["conteudo"], "original")
        self.assertEqual(salvar_indice.await_args.args[1]["status"], "excluida")

    async def test_busca_de_mensagem_retorna_status_do_indice(self):
        with (
            patch.object(monitor, "carregar", new=AsyncMock(return_value={
                "user_id": 42, "channel_id": 77, "timestamp": 1_800_000_000,
                "status": "excluida",
            })),
            patch.object(monitor, "definir_expiracao", new=AsyncMock()),
        ):
            registro = await monitor.buscar_mensagem(GUILD_ID, 9001)
        self.assertEqual(registro["status"], "excluida")


class TestListenersDeExclusao(unittest.IsolatedAsyncioTestCase):
    async def test_raw_nao_reprocessa_mensagem_ja_excluida(self):
        cog = Logs(Mock())
        payload = Mock(guild_id=GUILD_ID, message_id=9001)
        with (
            patch("cogs.logs.monitoramento_membros.buscar_mensagem", new=AsyncMock(return_value={
                "user_id": 42, "status": "excluida",
            })),
            patch("cogs.logs.monitoramento_membros.registrar_mensagem", new=AsyncMock()) as registrar,
        ):
            await cog.on_raw_message_delete(payload)
        registrar.assert_not_awaited()

    async def test_evento_em_lote_ignora_mensagem_ja_excluida(self):
        cog = Logs(Mock())
        payload = Mock(
            guild_id=GUILD_ID, channel_id=77, message_ids={9001},
            cached_messages=[],
        )
        with (
            patch("cogs.logs.monitoramento_membros.buscar_mensagem", new=AsyncMock(return_value={
                "user_id": 42, "status": "excluida",
            })),
            patch("cogs.logs.monitoramento_membros.registrar_mensagem", new=AsyncMock()) as registrar,
        ):
            await cog.on_raw_bulk_message_delete(payload)
        registrar.assert_not_awaited()

    async def test_listener_com_cache_nao_reprocessa_mensagem_ja_excluida(self):
        cog = Logs(Mock())
        mensagem = Mock(
            author=Mock(bot=False, id=42),
            guild=Mock(id=GUILD_ID),
            id=9001,
        )
        with (
            patch("cogs.logs.monitoramento_membros.buscar_mensagem", new=AsyncMock(return_value={
                "user_id": 42, "status": "excluida",
            })),
            patch("cogs.logs.monitoramento_membros.registrar_mensagem", new=AsyncMock()) as registrar,
        ):
            await cog.on_message_delete(mensagem)
        registrar.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
