import unittest
from unittest.mock import AsyncMock, patch

from cogs import eventos


class TestIntegridadeEventos(unittest.IsolatedAsyncioTestCase):
    def test_resumo_servidor_contabiliza_presencas_e_voz(self):
        from types import SimpleNamespace
        online = SimpleNamespace(id=1, bot=False, status=eventos.discord.Status.online)
        idle = SimpleNamespace(id=2, bot=False, status=eventos.discord.Status.idle)
        dnd = SimpleNamespace(id=3, bot=False, status=eventos.discord.Status.dnd)
        offline = SimpleNamespace(id=4, bot=False, status=eventos.discord.Status.offline)
        bot = SimpleNamespace(id=5, bot=True, status=eventos.discord.Status.online)
        canal = SimpleNamespace(members=[online, bot])
        guild = SimpleNamespace(members=[online, idle, dnd, offline, bot], member_count=5, voice_channels=[canal], stage_channels=[])

        resumo = eventos._resumo_servidor(guild)

        self.assertEqual(resumo["total"], 5)
        self.assertEqual(resumo["humanos_cache"], 4)
        self.assertEqual(resumo["bots_cache"], 1)
        self.assertEqual(resumo["online"], 3)
        self.assertEqual(resumo["ausentes"], 1)
        self.assertEqual(resumo["ocupados"], 1)
        self.assertEqual(resumo["offline_cache"], 1)
        self.assertEqual(resumo["voz"], 1)
        self.assertTrue(resumo["cache_completo"])

    def test_barra_progresso_limita_valores(self):
        self.assertEqual(eventos._barra_progresso(5, 10), "█████░░░░░")
        self.assertEqual(eventos._barra_progresso(15, 10), "██████████")
        self.assertEqual(eventos._barra_progresso(0, 10), "░░░░░░░░░░")

    async def test_storage_raiz_invalido_retorna_dicionario_vazio(self):
        with patch.object(eventos, "carregar", new=AsyncMock(return_value=[])):
            dados = await eventos._todos_eventos()

        self.assertEqual(dados, {})

    async def test_salvamento_nao_persiste_estrutura_raiz_invalida(self):
        with patch.object(eventos, "salvar", new=AsyncMock()) as salvar:
            await eventos._salvar_eventos(["inválido"])

        salvar.assert_awaited_once_with(eventos.ARQUIVO, {})

    async def test_evento_corrompido_nao_pode_ser_reutilizado_como_registro(self):
        dados = {"123": "registro inválido"}
        with patch.object(eventos, "_todos_eventos", new=AsyncMock(return_value=dados)), patch.object(
            eventos, "_salvar_eventos", new=AsyncMock()
        ) as salvar:
            # A deleção de um evento sem registro válido deve terminar sem exceção.
            cog = object.__new__(eventos.Eventos)
            evento = type("Evento", (), {"id": 123})()
            await eventos.Eventos.on_scheduled_event_delete(cog, evento)

        salvar.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
