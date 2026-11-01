import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.missoes import Missoes, SeletorMissaoProvaView, EnviarProvaMissaoModal
from utils import ranking_missoes_jogos


class TestRankingPanelEditLimit(unittest.IsolatedAsyncioTestCase):
    async def test_replaces_panel_when_discord_edit_limit_is_reached(self):
        guild = Mock()
        guild.id = 1563995879981981817

        canal = Mock()
        mensagem_antiga = Mock()
        mensagem_antiga.id = 111
        mensagem_antiga.embeds = []
        mensagem_antiga.edit = AsyncMock(
            side_effect=discord.HTTPException(
                response=SimpleNamespace(status=400, reason="Bad Request"),
                message={
                    "code": 30046,
                    "message": "Maximum number of edits to messages has been reached",
                },
            )
        )
        mensagem_antiga.delete = AsyncMock()

        mensagem_nova = Mock()
        mensagem_nova.id = 222
        mensagem_nova.pin = AsyncMock()

        canal.fetch_message = AsyncMock(return_value=mensagem_antiga)
        canal.send = AsyncMock(return_value=mensagem_nova)
        cog = Missoes.__new__(Missoes)

        with (
            patch("cogs.missoes.get_config", new=AsyncMock(return_value={})),
            patch.object(cog, "_resolver_canal", new=AsyncMock(return_value=canal)),
            patch.object(cog, "_montar_painel_ranking", new=AsyncMock(return_value=Mock())),
            patch.object(
                ranking_missoes_jogos,
                "obter_paineis",
                new=AsyncMock(return_value={"ranking": 111}),
            ),
            patch.object(
                ranking_missoes_jogos, "salvar_painel", new=AsyncMock()
            ) as salvar_painel,
        ):
            await cog._atualizar_ranking_geral(guild)

        canal.send.assert_awaited_once()
        salvar_painel.assert_awaited_once_with(guild.id, "ranking", 222)
        mensagem_nova.pin.assert_awaited_once()
        mensagem_antiga.delete.assert_awaited_once()


class TestMissionEvidenceSelector(unittest.TestCase):
    def setUp(self):
        self.atividades = [
            {
                "id": f"NM{indice:03d}",
                "titulo": f"Operação {indice:03d}",
                "tipo": "missao",
                "recompensa_xp": 25,
                "ativa": True,
            }
            for indice in range(30)
        ]

    def test_selector_shows_up_to_25_active_missions_per_page(self):
        view = SeletorMissaoProvaView(Mock(), 123, "missao", self.atividades)
        seletor = next(item for item in view.children if hasattr(item, "options"))
        self.assertEqual(len(seletor.options), 25)
        self.assertEqual(seletor.options[0].value, "NM000")
        self.assertEqual(seletor.options[-1].value, "NM024")
        self.assertTrue(view.pagina_anterior.disabled)
        self.assertFalse(view.proxima_pagina.disabled)

    def test_selector_paginates_remaining_missions(self):
        view = SeletorMissaoProvaView(Mock(), 123, "missao", self.atividades, pagina=1)
        seletor = next(item for item in view.children if hasattr(item, "options"))
        self.assertEqual(len(seletor.options), 5)
        self.assertEqual(seletor.options[0].value, "NM025")
        self.assertEqual(seletor.options[-1].value, "NM029")
        self.assertFalse(view.pagina_anterior.disabled)
        self.assertTrue(view.proxima_pagina.disabled)

    def test_evidence_modal_keeps_selected_mission_code(self):
        modal = EnviarProvaMissaoModal(Mock(), "NM007")
        self.assertEqual(modal.missao_id_selecionada, "NM007")



if __name__ == "__main__":
    unittest.main()
