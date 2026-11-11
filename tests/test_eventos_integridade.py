import unittest
from unittest.mock import AsyncMock, patch

from cogs import eventos


class TestIntegridadeEventos(unittest.IsolatedAsyncioTestCase):
    def test_resumo_servidor_mostra_somente_total_de_membros(self):
        from types import SimpleNamespace
        guild = SimpleNamespace(members=[SimpleNamespace(id=1)], member_count=125)

        resumo = eventos._resumo_servidor(guild)

        self.assertEqual(resumo, {"total": 125})

    def test_classifica_sorteio_em_meta_atingida(self):
        from datetime import datetime, timezone
        inicio = datetime(2026, 11, 10, 12, tzinfo=timezone.utc).timestamp()
        fim = datetime(2026, 11, 10, 14, tzinfo=timezone.utc).timestamp()
        meta = {"alvo": 100, "descricao": "Meta centenária", "atingido_em": inicio + 3600}
        sorteio = {"criado_em": inicio, "encerrado_em": fim}
        contextos = eventos._classificar_sorteio_historico(sorteio, [meta], [])

        self.assertTrue(any("Meta: Meta centenária" in item for item in contextos))

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
