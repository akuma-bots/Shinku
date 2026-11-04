import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.painel_administrativo import (
    CentralAdministrativaView,
    PainelAdministrativo,
    PainelAdministrativoView,
    SECOES_ADMINISTRATIVAS,
    _tem_acesso,
)


class TestPainelAdministrativoCentral(unittest.IsolatedAsyncioTestCase):
    def test_painel_publico_e_persistente_sem_comando_slash(self):
        painel = PainelAdministrativoView(SimpleNamespace())
        self.assertIsNone(painel.timeout)
        self.assertEqual(len(painel.children), 1)
        self.assertEqual(
            painel.children[0].custom_id,
            "nemesis:administracao:central:abrir",
        )
        self.assertEqual(PainelAdministrativo.__cog_app_commands__, [])

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

    async def test_seletor_administrativo_reconhece_clique_antes_de_carregar_secao(self):
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
        self.assertEqual(interaction.edit_original_response.await_args.kwargs["embed"].title, "Membros")

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

    def test_operacoes_apontam_apenas_para_canais_oficiais_confirmados(self):
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
