import unittest

import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.painel_administrativo import (
    CentralAdministrativaView,
    PainelAdministrativo,
    PainelAdministrativoView,
    SECOES_ADMINISTRATIVAS,
    _tem_acesso,
)


def _itens_aninhados(view):
    pendentes = [(item, None) for item in view.children]
    while pendentes:
        item, pai = pendentes.pop(0)
        yield item, pai
        for filho in getattr(item, "children", ()) or ():
            pendentes.append((filho, item))


def _nova_view(interaction):
    return interaction.edit_original_response.await_args.kwargs["view"]


class TestPainelAdministrativoCentral(unittest.IsolatedAsyncioTestCase):
    def test_painel_publico_e_persistente_sem_comando_slash(self):
        painel = PainelAdministrativoView(SimpleNamespace())
        self.assertIsNone(painel.timeout)
        botoes = [
            item for item, _ in _itens_aninhados(painel)
            if getattr(item, "custom_id", None) == "nemesis:administracao:central:abrir"
        ]
        self.assertEqual(len(botoes), 1)
        self.assertEqual(PainelAdministrativo.__cog_app_commands__, [])

    def test_painel_publico_aninha_botao_no_container_components_v2(self):
        painel = PainelAdministrativoView(SimpleNamespace())
        self.assertEqual(len(painel.children), 1)
        container = painel.children[0]
        self.assertIsInstance(container, discord.ui.Container)
        controles = [
            (item, pai) for item, pai in _itens_aninhados(painel)
            if isinstance(item, (discord.ui.Button, discord.ui.Select))
        ]
        self.assertEqual(len(controles), 1)
        botao, linha = controles[0]
        self.assertIsInstance(linha, discord.ui.ActionRow)
        self.assertIn(linha, container.children)
        self.assertEqual(botao.custom_id, "nemesis:administracao:central:abrir")

    def test_central_privada_aninha_seletor_links_e_acoes_no_mesmo_cartao(self):
        bot = SimpleNamespace(get_cog=lambda _nome: None)
        view = CentralAdministrativaView(
            bot,
            owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
            chave="operacoes",
            atalhos=[("Missões", "https://discord.com/channels/1/2")],
            octogono=True,
        )
        self.assertEqual(len(view.children), 1)
        container = view.children[0]
        self.assertIsInstance(container, discord.ui.Container)
        controles = [
            (item, pai) for item, pai in _itens_aninhados(view)
            if isinstance(item, (discord.ui.Button, discord.ui.Select))
        ]
        self.assertGreaterEqual(len(controles), 3)
        for controle, linha in controles:
            with self.subTest(controle=type(controle).__name__, custom_id=controle.custom_id):
                self.assertIsInstance(linha, discord.ui.ActionRow)
                self.assertIn(linha, container.children)
        self.assertTrue(any(isinstance(item, discord.ui.Select) for item, _ in controles))
        self.assertTrue(any(
            isinstance(item, discord.ui.Button) and item.style == discord.ButtonStyle.link
            for item, _ in controles
        ))
        self.assertTrue(any(
            isinstance(item, discord.ui.Button) and item.style == discord.ButtonStyle.primary
            for item, _ in controles
        ))

    def test_central_privada_tem_seis_areas_de_navegacao(self):
        view = CentralAdministrativaView(
            SimpleNamespace(),
            owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        self.assertEqual(view.timeout, 300)
        self.assertEqual(len(view.seletor.options), 6)
        self.assertEqual(
            {opcao.value for opcao in view.seletor.options},
            set(SECOES_ADMINISTRATIVAS),
        )
        itens = list(_itens_aninhados(view))
        self.assertTrue(any(item is view.seletor and pai.__class__.__name__ == "ActionRow" for item, pai in itens))

    async def test_seletor_administrativo_atualiza_cartao_components_v2(self):
        view = CentralAdministrativaView(
            SimpleNamespace(), owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        view.seletor._values = ["membros"]
        interaction = SimpleNamespace(
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )

        async def carregar_secao(_bot, _guild, _chave):
            interaction.response.defer.assert_awaited_once_with()
            return (SimpleNamespace(title="Membros"), [])

        with patch("cogs.painel_administrativo._embed_secao", AsyncMock(side_effect=carregar_secao)):
            await view._selecionar_secao(interaction)
        interaction.edit_original_response.assert_awaited_once()
        nova = _nova_view(interaction)
        self.assertIsInstance(nova, discord.ui.LayoutView)
        self.assertTrue(any("Membros" in getattr(item, "content", "") for item, _ in _itens_aninhados(nova)))

    async def test_inteligencia_de_operacoes_aparece_apenas_para_octogono(self):
        bot = SimpleNamespace(get_cog=lambda _nome: None)
        view = CentralAdministrativaView(
            bot, owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        view.seletor._values = ["operacoes"]
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        with (
            patch("cogs.painel_administrativo._embed_secao", AsyncMock(return_value=(SimpleNamespace(title="Operações"), []))),
            patch("cogs.painel_administrativo.membro_tem_octogono", return_value=True),
        ):
            await view._selecionar_secao(interaction)
        nova = _nova_view(interaction)
        botao = next(
            item for item, _ in _itens_aninhados(nova)
            if getattr(item, "label", None) == "Inteligência de operações"
        )
        self.assertEqual(botao.style, discord.ButtonStyle.primary)

        view_nao_octogono = CentralAdministrativaView(
            bot, owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        view_nao_octogono.seletor._values = ["operacoes"]
        with (
            patch("cogs.painel_administrativo._embed_secao", AsyncMock(return_value=(SimpleNamespace(title="Operações"), []))),
            patch("cogs.painel_administrativo.membro_tem_octogono", return_value=False),
        ):
            await view_nao_octogono._selecionar_secao(interaction)
        nova_sem_octogono = _nova_view(interaction)
        self.assertFalse(any(
            getattr(item, "label", None) == "Inteligência de operações"
            for item, _ in _itens_aninhados(nova_sem_octogono)
        ))

    async def test_botao_inteligencia_encaminha_para_modulo_original(self):
        cog_missoes = SimpleNamespace(enviar_painel_inteligencia=AsyncMock())
        bot = SimpleNamespace(get_cog=lambda nome: cog_missoes if nome == "Missoes" else None)
        view = CentralAdministrativaView(
            bot, owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        view.seletor._values = ["operacoes"]
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        with (
            patch("cogs.painel_administrativo._embed_secao", AsyncMock(return_value=(SimpleNamespace(title="Operações"), []))),
            patch("cogs.painel_administrativo.membro_tem_octogono", return_value=True),
        ):
            await view._selecionar_secao(interaction)
        botao = next(
            item for item, _ in _itens_aninhados(_nova_view(interaction))
            if getattr(item, "label", None) == "Inteligência de operações"
        )
        clique = SimpleNamespace()
        with patch("cogs.painel_administrativo._tem_acesso", return_value=True):
            await botao.callback(clique)
        cog_missoes.enviar_painel_inteligencia.assert_awaited_once_with(clique)

    def test_paineis_administrativos_migrados_nao_sao_comandos_slash(self):
        from cogs.formularios import Formularios
        from cogs.gestao_missoes import GestaoMissoes
        from cogs.revisoes import Revisoes
        from cogs.status_sistema import StatusSistema
        for cog, metodo in (
            (Formularios, "formulario_central"),
            (GestaoMissoes, "central_missoes"),
            (Revisoes, "painel_provas"),
            (StatusSistema, "status"),
            (StatusSistema, "diagnostico"),
        ):
            with self.subTest(cog=cog.__name__, metodo=metodo):
                self.assertFalse(hasattr(getattr(cog, metodo), "__command__"))

    async def test_acoes_de_operacoes_abrem_paineis_dos_cogs(self):
        formularios = SimpleNamespace(formulario_central=AsyncMock())
        gestao = SimpleNamespace(central_missoes=AsyncMock())
        revisoes = SimpleNamespace(painel_provas=AsyncMock())
        cogs = {"Formularios": formularios, "GestaoMissoes": gestao, "Revisoes": revisoes}
        bot = SimpleNamespace(get_cog=lambda nome: cogs.get(nome))
        view = CentralAdministrativaView(bot, owner_id=123, guild=SimpleNamespace(id=1563995879981981817))
        view.seletor._values = ["operacoes"]
        interacao_secao = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        with (
            patch("cogs.painel_administrativo._embed_secao", AsyncMock(return_value=(SimpleNamespace(title="Operações"), []))),
            patch("cogs.painel_administrativo.membro_tem_octogono", return_value=True),
        ):
            await view._selecionar_secao(interacao_secao)
        botao = next(item for item, _ in _itens_aninhados(_nova_view(interacao_secao)) if getattr(item, "label", "") == "Processos seletivos")
        clique = SimpleNamespace()
        with patch("cogs.painel_administrativo._tem_acesso", return_value=True):
            await botao.callback(clique)
        formularios.formulario_central.assert_awaited_once_with(clique)

    async def test_acoes_de_sistemas_abrem_status_e_diagnostico(self):
        status = SimpleNamespace(status=AsyncMock(), diagnostico=AsyncMock())
        bot = SimpleNamespace(get_cog=lambda nome: status if nome == "StatusSistema" else None)
        view = CentralAdministrativaView(bot, owner_id=123, guild=SimpleNamespace(id=1563995879981981817))
        view.seletor._values = ["sistemas"]
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        with patch("cogs.painel_administrativo._embed_secao", AsyncMock(return_value=(SimpleNamespace(title="Sistemas"), []))):
            await view._selecionar_secao(interaction)
        labels = {getattr(item, "label", "") for item, _ in _itens_aninhados(_nova_view(interaction))}
        self.assertIn("Saúde do sistema", labels)
        self.assertIn("Diagnóstico do armazenamento", labels)

    def test_areas_tem_destinos_de_auditoria_e_descricao(self):
        for chave, secao in SECOES_ADMINISTRATIVAS.items():
            with self.subTest(secao=chave):
                self.assertTrue(secao["titulo"])
                self.assertTrue(secao["descricao"])
                self.assertIsInstance(secao["topicos"], tuple)
                self.assertIsInstance(secao["canais"], tuple)
        self.assertIn("historico_membros", SECOES_ADMINISTRATIVAS["membros"]["topicos"])
        self.assertIn("missoes", SECOES_ADMINISTRATIVAS["operacoes"]["topicos"])
        self.assertIn("seguranca", SECOES_ADMINISTRATIVAS["seguranca"]["topicos"])
        self.assertNotIn("automod", SECOES_ADMINISTRATIVAS["seguranca"]["topicos"])
        self.assertIn("integracoes", SECOES_ADMINISTRATIVAS["sistemas"]["topicos"])

    def test_operacoes_preservam_canais_oficiais_e_operacionais_configurados(self):
        canais = dict(SECOES_ADMINISTRATIVAS["operacoes"]["canais"])
        self.assertEqual(canais, {
            "Missões": 1563995881315897549,
            "Central de missões": 1556543214885019668,
            "Envio de provas": 1556543417843056641,
            "Desafios competitivos": 1545834386128375909,
            "Agenda": 1563995880623841337,
            "Inscrições": 1563995880623841338,
            "Divisões": 1563995880833421511,
            "Parcerias": 1563995880833421513,
        })

    def test_dossie_nao_promete_auditoria_de_cargos_no_historico_individual(self):
        descricao = SECOES_ADMINISTRATIVAS["membros"]["descricao"].casefold()
        self.assertIn("auditoria de cargos permanece separada", descricao)
        self.assertNotIn("alterações de cargos fazem parte do histórico", descricao)

    def test_autorizacao_exige_servidor_e_lideranca(self):
        membro = SimpleNamespace(id=123)
        with patch("cogs.painel_administrativo.membro_tem_lideranca", return_value=True):
            self.assertTrue(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro)))
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1, user=membro)))
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro), owner_id=456))
        with patch("cogs.painel_administrativo.membro_tem_lideranca", return_value=False):
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro)))


if __name__ == "__main__":
    unittest.main()
