import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from cogs.tickets import (
    _montar_select,
    _card_central_tickets,
    FecharTicketView,
)


def _controles_aninhados(view):
    pendentes = [(item, None) for item in view.children]
    while pendentes:
        item, pai = pendentes.pop(0)
        if isinstance(item, (discord.ui.Button, discord.ui.Select,
                             discord.ui.ChannelSelect, discord.ui.RoleSelect)):
            yield item, pai
        for filho in getattr(item, "children", ()) or ():
            pendentes.append((filho, item))


class TestTicketPanelEmbedDesign(unittest.IsolatedAsyncioTestCase):
    async def test_painel_publico_usa_components_v2_com_seletor_no_cartao(self):
        tipos = [
            {
                "valor": "suporte",
                "label": "Suporte à comunidade",
                "descricao": "Ajuda com dúvidas e dificuldades.",
                "emoji": "🛟",
            },
            {
                "valor": "recrutamento",
                "label": "Recrutamento e admissão",
                "descricao": "Processos de ingresso na organização.",
                "emoji": "✦",
            },
        ]
        with (
            patch("cogs.tickets.get_config", new=AsyncMock(return_value={})),
            patch("cogs.tickets.tickets.get_tipos", new=AsyncMock(return_value=tipos)),
        ):
            view = await _montar_select(1563995879981981817)

        self.assertIsInstance(view, discord.ui.LayoutView)
        self.assertEqual(len(view.children), 1)
        container = view.children[0]
        self.assertIsInstance(container, discord.ui.Container)
        texto = "\\n".join(
            getattr(item, "content", "")
            for item in container.children
            if isinstance(item, discord.ui.TextDisplay)
        )
        self.assertIn("CENTRAL DE ATENDIMENTO", texto)
        self.assertIn("Suporte à comunidade", texto)
        controles = list(_controles_aninhados(view))
        self.assertEqual(len(controles), 1)
        seletor, linha = controles[0]
        self.assertIsInstance(seletor, discord.ui.Select)
        self.assertIsInstance(linha, discord.ui.ActionRow)
        self.assertIn(linha, container.children)
        self.assertEqual(seletor.custom_id, "ticket:abrir_select")
        self.assertEqual([opcao.value for opcao in seletor.options], ["suporte", "recrutamento"])

    def test_cartao_da_central_de_gestao_aninha_todos_os_controles(self):
        origem = discord.ui.View(timeout=300)
        botao = discord.ui.Button(label="Atualizar", custom_id="ticket:atualizar")
        seletor = discord.ui.Select(
            placeholder="Categoria",
            options=[discord.SelectOption(label="Suporte", value="suporte")],
            custom_id="ticket:categoria",
        )
        botao.callback = AsyncMock()
        seletor.callback = AsyncMock()
        origem.add_item(botao)
        origem.add_item(seletor)

        cartao = _card_central_tickets(origem, titulo="CENTRAL DE GESTÃO")
        self.assertIsInstance(cartao, discord.ui.LayoutView)
        self.assertEqual(len(cartao.children), 1)
        container = cartao.children[0]
        self.assertIsInstance(container, discord.ui.Container)
        controles = list(_controles_aninhados(cartao))
        self.assertEqual(len(controles), 2)
        for controle, linha in controles:
            self.assertIsInstance(linha, discord.ui.ActionRow)
            self.assertIn(linha, container.children)
        ids = {controle.custom_id for controle, _ in controles}
        self.assertEqual(ids, {"ticket:atualizar", "ticket:categoria"})

        botao_clonado = next(
            controle for controle, _ in controles
            if controle.custom_id == "ticket:atualizar"
        )
        seletor_clonado = next(
            controle for controle, _ in controles
            if controle.custom_id == "ticket:categoria"
        )
        self.assertIs(botao_clonado.callback, botao.callback)
        seletor_clonado._values = ["suporte"]
        interaction = SimpleNamespace()
        await seletor_clonado.callback(interaction)
        self.assertEqual(seletor._values, ["suporte"])
        seletor.callback.assert_awaited_once_with(interaction)

    def test_controles_persistentes_incluem_acoes_de_atendimento(self):
        view = FecharTicketView()
        ids = {item.custom_id for item in view.children}
        self.assertIn("ticket:assumir", ids)
        self.assertIn("fechar_ticket_btn", ids)
        self.assertIn("ticket:adicionar_participante", ids)
        self.assertIn("ticket:solicitar_equipe", ids)


if __name__ == "__main__":
    unittest.main()
