import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.missoes import Missoes
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
            await cog._atualizar_ranking_jogo(guild, "shigaku")

        canal.send.assert_awaited_once()
        salvar_painel.assert_awaited_once_with(guild.id, "ranking", 222)
        mensagem_nova.pin.assert_awaited_once()
        mensagem_antiga.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
