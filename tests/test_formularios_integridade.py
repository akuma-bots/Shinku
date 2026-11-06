import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils import formularios


class TestIntegridadeFormularios(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_e_tratado_como_vazio(self):
        with patch.object(formularios, "carregar", new=AsyncMock(return_value=[])):
            self.assertEqual(await formularios._tudo_formularios(), {})
            self.assertEqual(await formularios._tudo_respostas(), {})

    async def test_listagem_filtra_registros_corrompidos(self):
        dados_formularios = {"123": [None, "inválido", {"id": "f1", "nome": "Form"}]}
        dados_respostas = {"123": [None, "inválido", {"id": "r1", "formulario_id": "f1", "status": "pendente"}]}
        with patch.object(formularios, "_tudo_formularios", new=AsyncMock(return_value=dados_formularios)), patch.object(
            formularios, "_tudo_respostas", new=AsyncMock(return_value=dados_respostas)
        ):
            forms = await formularios.listar_formularios(123)
            respostas = await formularios.listar_respostas(123, status="pendente")

        self.assertEqual([item["id"] for item in forms], ["f1"])
        self.assertEqual([item["id"] for item in respostas], ["r1"])

    async def test_decisoes_concorrentes_nao_aprovam_e_rejeitam_a_mesma_resposta(self):
        dados = {"123": [{
            "id": "r1",
            "formulario_id": "f1",
            "status": "pendente",
            "autor_id": 456,
            "avaliacoes": [{"media": 4.0}],
        }]}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_respostas_guild", new=AsyncMock()
        ) as salvar:
            resultados = await asyncio.gather(
                formularios.definir_status_resposta(123, "r1", "aprovada", 1),
                formularios.definir_status_resposta(123, "r1", "recusada", 2),
            )

        aplicadas = [resultado for resultado in resultados if resultado is not None]
        self.assertEqual(len(aplicadas), 1)
        self.assertIn(dados["123"][0]["status"], {"aprovada", "recusada"})
        salvar.assert_awaited_once()

    async def test_atualizacao_de_formulario_pode_marcar_versao_de_semeadura(self):
        formulario = {"id": "f1", "nome": "Staff", "versao_automatico": 0}
        dados = {"123": [formulario]}
        with patch.object(formularios, "_tudo_formularios", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_formularios_guild", new=AsyncMock()
        ):
            atualizado = await formularios.atualizar_formulario(123, "f1", versao_automatico=1)
        self.assertEqual(atualizado["versao_automatico"], 1)

    async def test_criacao_concorrente_de_formularios_nao_perde_atualizacao(self):
        import copy
        dados = {"123": []}

        async def carregar_catalogo():
            return copy.deepcopy(dados)

        async def salvar_catalogo(guild_id, lista):
            dados[str(guild_id)] = copy.deepcopy(lista)

        with patch.object(formularios, "_tudo_formularios", new=AsyncMock(side_effect=carregar_catalogo)), patch.object(
            formularios, "_salvar_formularios_guild", new=AsyncMock(side_effect=salvar_catalogo)
        ):
            await asyncio.gather(
                formularios.criar_formulario(123, "Staff", "Staff", "Descrição", None, 1),
                formularios.criar_formulario(123, "Parcerias", "Parcerias", "Descrição", None, 2),
            )
        self.assertEqual({item["nome"] for item in dados["123"]}, {"Staff", "Parcerias"})

    async def test_editar_pergunta_nao_altera_snapshot_da_candidatura_existente(self):
        pergunta = {"texto": "Pergunta antiga", "tipo": "paragrafo"}
        formulario = {"id": "f1", "paginas": [{"titulo": "Etapa 1", "perguntas": [pergunta]}]}
        resposta = {"itens": [{"pergunta": "Pergunta antiga", "resposta": "Resposta"}]}
        dados = {"123": [formulario]}
        with patch.object(formularios, "_tudo_formularios", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_formularios_guild", new=AsyncMock()
        ):
            ok = await formularios.atualizar_pergunta(123, "f1", 0, "Pergunta nova")
        self.assertTrue(ok)
        self.assertEqual(pergunta["texto"], "Pergunta nova")
        self.assertEqual(resposta["itens"][0]["pergunta"], "Pergunta antiga")

    async def test_criar_resposta_impede_duas_candidaturas_pendentes_concorrentes(self):
        dados = {"123": []}
        formulario = {"id": "f1", "nome": "Form", "paginas": []}
        async def salvar(guild_id, lista):
            dados[str(guild_id)] = list(lista)

        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "get_formulario", new=AsyncMock(return_value=formulario)
        ), patch.object(formularios, "_salvar_respostas_guild", new=AsyncMock(side_effect=salvar)):
            resultados = await asyncio.gather(
                formularios.criar_resposta(123, "f1", 456, [], "Membro"),
                formularios.criar_resposta(123, "f1", 456, [], "Membro"),
            )
        self.assertEqual(sum(item is not None for item in resultados), 1)
        self.assertEqual(len(dados["123"]), 1)

    async def test_decisao_sem_avaliacao_estruturada_e_bloqueada(self):
        dados = {"123": [{"id": "r-no-review", "status": "pendente", "avaliacoes": []}]}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_respostas_guild", new=AsyncMock()
        ) as salvar:
            resultado = await formularios.definir_status_resposta(123, "r-no-review", "aprovada", 99, "Motivo")
        self.assertIsNone(resultado)
        salvar.assert_not_awaited()

    async def test_limpeza_em_lote_grava_historico_de_decisao(self):
        resposta = {"id": "r-old", "status": "pendente", "autor_id": 456}
        dados = {"123": [resposta]}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_respostas_guild", new=AsyncMock()
        ) as salvar:
            resultado = await formularios.recusar_respostas_pendentes(123, 999, motivo="Limpeza inicial")
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resposta["historico_decisoes"][0]["revisor_id"], 999)
        self.assertEqual(resposta["historico_decisoes"][0]["motivo"], "Limpeza inicial")
        salvar.assert_awaited_once()

    async def test_criar_resposta_recupera_lista_corrompida(self):
        dados = {"123": "lista inválida"}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "get_formulario", new=AsyncMock(return_value={"nome": "Form", "paginas": []})
        ), patch.object(formularios, "_salvar_respostas_guild", new=AsyncMock()) as salvar:
            resposta = await formularios.criar_resposta(123, "f1", 456, [], "Membro")

        self.assertEqual(resposta["status"], "pendente")
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()


class TestRespostaInteracaoFormulario(unittest.IsolatedAsyncioTestCase):
    async def test_botao_de_decisao_abre_modal_privado_com_validacao_administrativa(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import discord
        from cogs.formularios import Formularios, ModalDecisaoFormulario, PREFIXO_APROVAR

        response = SimpleNamespace(send_modal=AsyncMock())
        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": PREFIXO_APROVAR + "resp-audit"},
            response=response,
            guild=SimpleNamespace(id=123),
            user=SimpleNamespace(id=456),
        )
        cog = object.__new__(Formularios)
        cog.bot = SimpleNamespace(guilds=[])

        with patch("cogs.formularios.membro_tem_lideranca", return_value=True), patch(
            "cogs.formularios.formularios.get_resposta",
            new=AsyncMock(return_value={"id": "resp-audit", "status": "pendente", "avaliacoes": [{"media": 4.5}]}),
        ):
            await cog.on_interaction(interaction)

        response.send_modal.assert_awaited_once()
        self.assertIsInstance(response.send_modal.await_args.args[0], ModalDecisaoFormulario)
