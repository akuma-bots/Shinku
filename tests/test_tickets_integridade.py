import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import storage, tickets
from cogs.tickets import AvaliacaoTicketButton, AvaliacaoTicketView, CentralTicketsView, PersonalizarPainelTicketModal, Tickets


class TestTicketsIntegridade(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.patchers = [
            patch.object(storage, "DATA_DIR", Path(self.tempdir.name)),
            patch.object(storage, "USANDO_UPSTASH", False),
            patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", False),
        ]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)

    async def test_gestao_de_tickets_usa_central_sem_comandos_independentes(self):
        comandos = getattr(Tickets, "__cog_app_commands__", [])
        nomes = {comando.name for comando in comandos}
        self.assertNotIn("ticket-painel-configurar", nomes)
        self.assertNotIn("ticket-categoria-visual", nomes)

        central = CentralTicketsView(
            cog=None,
            guild=type("Guild", (), {"id": 123, "name": "NÊMESIS"})(),
            owner_id=456,
        )
        botoes = {
            item.label for item in central.children
            if getattr(item, "label", None)
        }
        self.assertIn("Personalizar painel", botoes)
        self.assertIn("Atualizar painel", botoes)
        self.assertIn("Fechar central", botoes)
        self.assertEqual(len(central.children), 5)

    async def test_central_carrega_seletor_de_categorias_para_edicao(self):
        central = CentralTicketsView(
            cog=None,
            guild=type("Guild", (), {"id": 123, "name": "NÊMESIS"})(),
            owner_id=456,
        )
        with patch(
            "cogs.tickets.tickets.get_tipos",
            new=unittest.mock.AsyncMock(return_value=[
                {"valor": "suporte", "label": "Suporte", "descricao": "Ajuda", "emoji": "⚙️"}
            ]),
        ):
            await central.configurar()
        self.assertIsNotNone(central.seletor_tipos)
        self.assertEqual(central.seletor_tipos.options[0].value, "suporte")
        self.assertEqual(len(central.children), 6)

    async def test_modal_de_painel_carrega_configuracao_atual(self):
        central = CentralTicketsView(
            cog=None,
            guild=type("Guild", (), {"id": 123, "name": "NÊMESIS"})(),
            owner_id=456,
        )
        modal = PersonalizarPainelTicketModal(
            central,
            {
                "ticket_painel_titulo": "Painel atual",
                "ticket_painel_descricao": "Descrição atual",
                "ticket_painel_banner_url": "https://example.com/banner.png",
            },
        )
        self.assertEqual(modal.titulo.default, "Painel atual")
        self.assertEqual(modal.descricao.default, "Descrição atual")
        self.assertEqual(modal.banner.default, "https://example.com/banner.png")

    async def test_botoes_de_avaliacao_sao_dinamicos_e_persistentes(self):
        view = AvaliacaoTicketView(123456, "a1b2c3d4", 200, 300)
        self.assertIsNone(view.timeout)
        self.assertEqual(len(view.children), 5)
        self.assertTrue(all(isinstance(item, AvaliacaoTicketButton) for item in view.children))
        self.assertTrue(
            view.children[0].template.match(
                "ticket:avaliar:123456:a1b2c3d4:5"
            )
        )

    async def test_topic_invalido_nao_e_reconhecido_como_ticket(self):
        self.assertIsNone(tickets.parse_topic("ticket-owner:abc:tipo:suporte"))
        self.assertIsNone(tickets.parse_topic("ticket-owner:123:tipo:" + "x" * 101))
        self.assertEqual(
            tickets.parse_topic("ticket-owner:123:tipo:suporte"),
            {"owner_id": "123", "tipo": "suporte"},
        )

    async def test_aberturas_concorrentes_do_mesmo_usuario_criam_um_registro(self):
        resultados = await asyncio.gather(*(
            tickets.criar_ticket(
                guild_id=100,
                usuario_id=200,
                tipo=f"tipo-{indice}",
                canal_id=1000 + indice,
                mensagem_id=2000 + indice,
            )
            for indice in range(20)
        ))
        registros = await tickets.listar_tickets(100, status="aberto")
        self.assertEqual(len(registros), 1)
        self.assertEqual(len({item["id"] for item in resultados}), 1)
        self.assertEqual(len({item["canal_id"] for item in resultados}), 1)

    async def test_atualizacoes_concorrentes_preservam_atendente_e_mensagem(self):
        ticket = await tickets.criar_ticket(101, 201, "suporte", 1001, 2001)
        await asyncio.gather(
            tickets.atualizar_ticket(101, ticket["id"], atendido_por_id=300),
            tickets.atualizar_ticket(101, ticket["id"], mensagem_id=4001),
            tickets.atualizar_ticket(101, ticket["id"], avaliacao_solicitada=True),
        )
        salvo = await tickets.get_ticket(101, ticket["id"])
        self.assertEqual(salvo["atendido_por_id"], 300)
        self.assertEqual(salvo["mensagem_id"], 4001)
        self.assertTrue(salvo["avaliacao_solicitada"])

    async def test_remover_responsavel_limpa_valor_persistido(self):
        ticket = await tickets.criar_ticket(102, 202, "suporte", 1002, 2002)
        await tickets.registrar_atendimento(102, ticket["id"], 302)
        atualizado = await tickets.remover_responsavel_atendimento(102, ticket["id"])
        self.assertIsNone(atualizado["atendido_por_id"])

    async def test_recuperacao_de_canal_e_idempotente_e_nao_reabre_fechado(self):
        primeiro = await tickets.sincronizar_canal_ticket(
            103, 1003, mensagem_id=2003, usuario_id=203, tipo="outro"
        )
        segundo = await tickets.sincronizar_canal_ticket(
            103, 1003, mensagem_id=2004, usuario_id=203, tipo="outro"
        )
        self.assertEqual(primeiro["id"], segundo["id"])
        self.assertEqual(len(await tickets.listar_tickets(103)), 1)
        await tickets.fechar_ticket(103, primeiro["id"], motivo="Fechado")
        terceiro = await tickets.sincronizar_canal_ticket(
            103, 1003, mensagem_id=2005, usuario_id=203, tipo="outro"
        )
        self.assertEqual(terceiro["status"], "fechado")

    async def test_avaliacao_so_pode_ser_registrada_uma_vez(self):
        ticket = await tickets.criar_ticket(108, 208, "suporte", 1008, 2008)
        await tickets.fechar_ticket(108, ticket["id"], motivo="Concluído")
        resultados = await asyncio.gather(*(
            tickets.registrar_avaliacao(
                108, ticket["id"], nota, f"Feedback {nota}"
            )
            for nota in range(1, 6)
        ))
        registradas = [item for item in resultados if item is not None]
        self.assertEqual(len(registradas), 1)
        salvo = await tickets.get_ticket(108, ticket["id"])
        self.assertIn(salvo["avaliacao"], range(1, 6))

    async def test_reserva_de_fechamento_impede_duplo_encerramento(self):
        ticket = await tickets.criar_ticket(105, 205, "suporte", 1005, 2005)
        resultados = await asyncio.gather(*(
            tickets.iniciar_fechamento_ticket(
                105, ticket["id"], fechado_por_id=300 + indice,
                motivo="Fechamento concorrente",
            )
            for indice in range(12)
        ))
        self.assertEqual(sum(bool(item) for item in resultados), 1)
        salvo = await tickets.get_ticket(105, ticket["id"])
        self.assertEqual(salvo["status"], "fechando")

    async def test_reserva_expirada_pode_ser_recuperada_e_finalizada(self):
        ticket = await tickets.criar_ticket(106, 206, "suporte", 1006, 2006)
        primeira = await tickets.iniciar_fechamento_ticket(
            106, ticket["id"], motivo="Primeira tentativa"
        )
        segunda = await tickets.iniciar_fechamento_ticket(
            106, ticket["id"], motivo="Tentativa recuperada"
        )
        self.assertTrue(primeira)
        self.assertFalse(segunda)
        await tickets.atualizar_ticket(
            106, ticket["id"], fechamento_iniciado_em=1
        )
        terceira = await tickets.iniciar_fechamento_ticket(
            106, ticket["id"], motivo="Retomada"
        )
        self.assertTrue(terceira)
        fechado = await tickets.finalizar_fechamento_ticket(106, ticket["id"])
        self.assertEqual(fechado["status"], "fechado")

    async def test_edicao_visual_de_categoria_nao_reverte_outras_edicoes(self):
        await tickets.adicionar_tipo(107, "Categoria Nova", "Original", "✦", False)
        await asyncio.gather(
            tickets.atualizar_tipo_visual(
                107, "categoria_nova", "⚔️", "Atualizada", "Nova Categoria"
            ),
            tickets.adicionar_tipo(
                107, "Outra Categoria", "Descrição", "◈", False
            ),
        )
        tipos = await tickets.get_tipos(107)
        por_valor = {item["valor"]: item for item in tipos}
        self.assertEqual(por_valor["categoria_nova"]["emoji"], "⚔️")
        self.assertEqual(por_valor["categoria_nova"]["label"], "Nova Categoria")
        self.assertIn("outra_categoria", por_valor)

    async def test_edicoes_concorrentes_de_categoria_nao_sobrescrevem(self):
        await asyncio.gather(*(
            tickets.adicionar_tipo(
                104, f"Categoria {indice}", "Descrição", "✦", False
            )
            for indice in range(15)
        ))
        tipos = await tickets.get_tipos(104)
        self.assertEqual(len(tipos), len(tickets.TIPOS_PADRAO) + 15)
        await asyncio.gather(*(
            tickets.remover_tipo(104, f"categoria_{indice}")
            for indice in range(5)
        ))
        tipos = await tickets.get_tipos(104)
        self.assertEqual(len(tipos), len(tickets.TIPOS_PADRAO) + 10)


if __name__ == "__main__":
    unittest.main()
