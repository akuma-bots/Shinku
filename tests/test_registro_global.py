import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from utils import registro_global


class TestRegistroGlobal(unittest.IsolatedAsyncioTestCase):
    def test_define_topicos_permanentes_configurados(self):
        essenciais = {
            "mensagens", "atendimento", "moderacao", "membros",
            "sistemas", "administracao", "seguranca", "formularios",
        }
        self.assertTrue(essenciais.issubset(registro_global.CATEGORIAS))
        self.assertGreaterEqual(len(registro_global.CATEGORIAS), 28)
        nomes = [nome for nome, _ in registro_global.CATEGORIAS.values()]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_acesso_inclui_octogono_e_staff_sem_cargos_competitivos(self):
        esperados = {
            1563995880015536193, 1563995880015536192, 1563995880015536191,
            1563995880015536190, 1563995880015536189, 1563995880007139428,
            1563995880007139427, 1563995880007139426, 1563995880007139425,
            1563995880007139424, 1563995880007139423, 1563995880007139422,
            1563995880007139421, 1563995880007139420, 1563995880007139419,
            1563995879998754946, 1563995879998754945,
        }
        self.assertEqual(registro_global.CARGOS_ACESSO_IDS, esperados)
        self.assertNotIn(1563995879998754943, registro_global.CARGOS_ACESSO_IDS)
        self.assertNotIn(1563995879990624373, registro_global.CARGOS_ACESSO_IDS)

    async def test_nao_provisiona_outros_servidores(self):
        guild = Mock()
        guild.id = 123
        self.assertEqual(await registro_global.garantir_topicos(guild), {})

    async def test_recusa_categoria_desconhecida(self):
        forum = Mock()
        forum.guild.id = registro_global.GUILD_NEMESIS_ID
        with self.assertRaises(ValueError):
            await registro_global._obter_topico(forum, "categoria-inexistente")

    def test_falha_fechado_se_forum_estiver_visivel_a_todos(self):
        guild = Mock()
        guild.default_role = object()
        forum = Mock()
        forum.guild = guild
        forum.overwrites_for.return_value = SimpleNamespace(view_channel=True)
        with self.assertRaises(PermissionError):
            registro_global.validar_privacidade(forum)

    def test_privacidade_exige_cargos_autorizados(self):
        guild = Mock()
        guild.default_role = object()
        guild.me = object()
        guild.get_role.side_effect = lambda role_id: SimpleNamespace(id=role_id, name=str(role_id))
        forum = Mock()
        forum.guild = guild
        forum.overwrites = {}
        forum.overwrites_for.return_value = SimpleNamespace(view_channel=False)
        forum.permissions_for.side_effect = lambda target: SimpleNamespace(
            view_channel=False, send_messages=True, send_messages_in_threads=True,
            manage_threads=True, create_public_threads=True,
        )
        with self.assertRaises(PermissionError):
            registro_global.validar_privacidade(forum)

    async def test_reutiliza_topico_salvo_sem_criar_outro(self):
        forum = Mock()
        forum.id = 456
        forum.guild.id = registro_global.GUILD_NEMESIS_ID
        thread = Mock()
        thread.id = 789
        thread.parent_id = forum.id
        thread.name = registro_global.CATEGORIAS["mensagens"][0]
        thread.archived = False
        thread.locked = False
        forum.threads = []
        async def sem_arquivados(limit=None):
            if False:
                yield None
        forum.archived_threads.side_effect = sem_arquivados
        forum.guild.get_thread.return_value = thread
        with patch.object(registro_global, "_ler_ids", new=AsyncMock(return_value={"mensagens": 789})), \
             patch.object(registro_global, "_salvar_id", new=AsyncMock()) as salvar:
            resultado = await registro_global._obter_topico(forum, "mensagens")
        self.assertIs(resultado, thread)
        forum.create_thread.assert_not_called()
        salvar.assert_not_awaited()

    async def test_renomeia_topico_legado_salvo_sem_perder_historico(self):
        forum = Mock()
        forum.id = 456
        forum.guild.id = registro_global.GUILD_NEMESIS_ID
        thread = Mock()
        thread.id = 789
        thread.parent_id = forum.id
        thread.name = "📌・Registros Antigos"
        thread.archived = True
        thread.locked = True
        forum.threads = []
        async def sem_arquivados(limit=None):
            if False:
                yield None
        forum.archived_threads.side_effect = sem_arquivados
        forum.guild.get_thread.return_value = thread
        with patch.object(registro_global, "_ler_ids", new=AsyncMock(return_value={"mensagens": 789})), \
             patch.object(registro_global, "_salvar_id", new=AsyncMock()) as salvar:
            resultado = await registro_global._obter_topico(forum, "mensagens")
        self.assertIs(resultado, thread)
        thread.edit.assert_awaited_once()
        self.assertEqual(thread.edit.await_args.kwargs["name"], registro_global.CATEGORIAS["mensagens"][0])
        self.assertFalse(thread.edit.await_args.kwargs["archived"])
        self.assertFalse(thread.edit.await_args.kwargs["locked"])
        salvar.assert_awaited_once_with(registro_global.GUILD_NEMESIS_ID, "mensagens", 789)


if __name__ == "__main__":
    unittest.main()
