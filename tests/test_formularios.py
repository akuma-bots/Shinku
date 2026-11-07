import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from cogs import formularios as cog_formularios
from cogs.formularios import _embeds_painel, _embeds_resposta, _paginas_modal, _limpar_sessoes_formularios
from utils import formularios as storage_formularios


class TestFormularios(unittest.IsolatedAsyncioTestCase):
    def test_descricao_longa_e_dividida_sem_ultrapassar_limite_do_discord(self):
        descricao = ("Texto da descrição da NÊMESIS.\n" * 500)
        embeds = _embeds_painel({
            "id": "teste",
            "titulo_painel": "Formulário de teste",
            "descricao_painel": descricao,
        })

        self.assertGreater(len(embeds), 1)
        self.assertTrue(all(embed.description for embed in embeds))
        self.assertTrue(all(len(embed.description) <= 4096 for embed in embeds))

    def test_sessoes_abandonadas_sao_removidas(self):
        cog_formularios.SESSOES_FORMULARIOS.clear()
        cog_formularios.SESSOES_FORMULARIOS[(1, 2, "antiga")] = {
            "formulario": {},
            "respostas": [],
            "atualizado_em": 50,
        }
        cog_formularios.SESSOES_FORMULARIOS[(1, 2, "recente")] = {
            "formulario": {},
            "respostas": [],
            "atualizado_em": 950,
        }

        _limpar_sessoes_formularios(agora=1000)

        self.assertNotIn((1, 2, "antiga"), cog_formularios.SESSOES_FORMULARIOS)
        self.assertIn((1, 2, "recente"), cog_formularios.SESSOES_FORMULARIOS)
        cog_formularios.SESSOES_FORMULARIOS.clear()

    def test_formulario_staff_tem_20_perguntas_em_quatro_etapas(self):
        formulario = cog_formularios.FORMULARIOS_AUTOMATICOS[0]
        self.assertEqual(len(cog_formularios._perguntas_flat(formulario)), 20)
        self.assertEqual(
            [len(pagina["perguntas"]) for pagina in cog_formularios._paginas_modal(formulario)],
            [5, 5, 5, 5],
        )

    def test_canal_de_recebimento_e_o_canal_oficial_configurado(self):
        self.assertEqual(
            cog_formularios.CANAL_RECEBIMENTO_CANDIDATURAS,
            1563995882540498996,
        )

    def test_etapas_com_mais_de_cinco_perguntas_sao_divididas_para_modais(self):
        formulario = {
            "paginas": [{
                "titulo": "Etapa única",
                "perguntas": [
                    {"id": str(i), "texto": f"Pergunta {i}"}
                    for i in range(12)
                ],
            }]
        }

        paginas = _paginas_modal(formulario)
        self.assertEqual([len(p["perguntas"]) for p in paginas], [5, 5, 2])

    async def test_candidatura_e_organizada_em_topico_individual_sem_dm_em_massa(self):
        cog = object.__new__(cog_formularios.Formularios)
        cog.bot = SimpleNamespace()
        thread = SimpleNamespace(
            id=987654,
            send=AsyncMock(),
        )
        canal = SimpleNamespace(
            id=1563995882540498996,
            create_thread=AsyncMock(return_value=thread),
        )
        guild = SimpleNamespace(
            id=1563995879981981817,
            name="NÊMESIS",
            get_channel=lambda _channel_id: canal,
            fetch_channel=AsyncMock(return_value=canal),
            get_role=lambda _role_id: None,
        )
        embed = discord.Embed(title="Dossiê de candidatura")
        view = object()
        with patch("cogs.formularios._embeds_resposta", return_value=[embed]), patch(
            "cogs.formularios._view_resposta", return_value=view
        ), patch("cogs.formularios.formularios.atualizar_metadados_resposta", new=AsyncMock()), patch(
            "utils.registro_global.registrar", new=AsyncMock()
        ):
            publicado = await cog.notificar_cargos(
                guild,
                {"id": "form-staff", "nome": "Staff", "cargos_notificar": []},
                {"id": "resp-123", "autor_id": 456, "nome": "Candidato"},
            )

        self.assertTrue(publicado)
        canal.create_thread.assert_awaited_once()
        thread.send.assert_awaited_once()
        self.assertNotIn("view", thread.send.await_args.kwargs)


    def test_central_de_formularios_inclui_seletor_privado_de_fichas_pendentes(self):
        cog = object.__new__(cog_formularios.Formularios)
        central = cog_formularios.CentralFormulariosView(
            cog,
            guild_id=123,
            usuario_id=456,
            lista=[{"id": "form-1", "nome": "Staff", "paginas": []}],
        )

        self.assertEqual(len(central.children), 5)
        self.assertEqual(
            central.children[3].custom_id,
            "nemesis:formularios:fila_pendentes",
        )
        self.assertEqual(
            central.children[3].options[0].value,
            "abrir_pendentes",
        )
        self.assertEqual(central.children[4].custom_id, "nemesis:formularios:historico_fichas")

    def test_gerenciamento_de_formularios_nao_registra_grupo_slash(self):
        from discord.ext import commands
        self.assertTrue(issubclass(cog_formularios.Formularios, commands.Cog))
        self.assertFalse(issubclass(cog_formularios.Formularios, commands.GroupCog))
        self.assertFalse(any(hasattr(cog_formularios.Formularios, nome) for nome in (
            "formulario_criar", "formulario_pagina_adicionar", "formulario_pagina_remover",
            "formulario_fila", "formulario_consultar", "formulario_avaliar",
            "formulario_historico", "formulario_cargo_adicionar", "formulario_cargo_remover",
        )))

    def test_configuracao_de_comissao_usa_seletor_de_cargos_e_botao_salvar(self):
        class Guild:
            id = 123
            roles = []
        cog = object.__new__(cog_formularios.Formularios)
        view = cog_formularios.GerenciarCargosView(cog, Guild(), 456, {"id": "form-1", "cargos_notificar": []})
        self.assertEqual(len(view.children), 2)
        self.assertTrue(any(isinstance(item, discord.ui.RoleSelect) for item in view.children))
        self.assertTrue(any(isinstance(item, discord.ui.Button) and item.label == "Salvar cargos" for item in view.children))

    def test_central_sem_formularios_ainda_oferece_criacao(self):
        cog = object.__new__(cog_formularios.Formularios)
        central = cog_formularios.CentralFormulariosView(cog, 123, 456, [])
        self.assertEqual(len(central.children), 1)
        self.assertEqual(central.children[0].label, "Novo formulário")

    def test_modal_de_criacao_e_edicao_respeita_limites_do_discord(self):
        cog = object.__new__(cog_formularios.Formularios)
        criar = cog_formularios.ModalCriarFormulario(cog, 123, 456)
        editar = cog_formularios.ModalEditarFormulario(cog, 123, 456, {
            "id": "form-1", "nome": "Staff", "titulo_painel": "Staff", "descricao_painel": "Descrição", "banner_url": ""
        })
        self.assertEqual(len(criar.children), 4)
        self.assertEqual(len(editar.children), 4)
        self.assertTrue(all(len(campo.label) <= 45 for campo in criar.children + editar.children))

    def test_dossie_usa_snapshot_das_perguntas_originais(self):
        formulario = {"nome": "Staff", "paginas": [["Pergunta editada depois"]]}
        resposta = {
            "id": "resp-snapshot", "autor_id": 456, "nome": "Candidato", "formTitulo": "Nome original do processo",
            "respostas": ["Resposta antiga"],
            "itens": [{"pergunta": "Pergunta original", "resposta": "Resposta antiga"}],
        }
        embeds = _embeds_resposta(formulario, resposta, SimpleNamespace(name="NÊMESIS"))
        texto = "\n".join(field.name + " " + field.value for embed in embeds for field in embed.fields)
        self.assertIn("Pergunta original", texto)
        self.assertNotIn("Pergunta editada depois", texto)
        self.assertIn("Nome original do processo", embeds[0].title)

    def test_historico_de_candidaturas_tem_paginacao_de_25_fichas(self):
        central = SimpleNamespace(usuario_id=456, formulario_id="form-1")
        respostas = [
            {"id": f"resp-{i}", "nome": f"Candidato {i}", "status": "aprovada" if i % 2 else "recusada"}
            for i in range(26)
        ]
        view = cog_formularios.FilaHistoricoView(central, respostas)
        self.assertEqual(view.total_paginas, 2)
        self.assertEqual(len(view.children[0].options), 25)
        view.pagina = 1
        view._montar()
        self.assertEqual(len(view.children[0].options), 1)

    def test_seletor_de_edicao_de_perguntas_e_paginado_em_blocos_de_25(self):
        cog = object.__new__(cog_formularios.Formularios)
        formulario = {"id": "f1", "paginas": [[f"Pergunta {i}" for i in range(26)]]}
        view = cog_formularios.EditarPerguntasView(cog, 123, 456, formulario)
        self.assertEqual(view.total_paginas, 2)
        self.assertEqual(len(view.children[0].options), 25)
        view.pagina = 1
        view._montar()
        self.assertEqual(len(view.children[0].options), 1)
        self.assertEqual(view.children[0].options[0].value, "25")

    def test_modal_de_perguntas_oferece_no_maximo_cinco_campos(self):
        cog = object.__new__(cog_formularios.Formularios)
        modal = cog_formularios.ModalAdicionarPerguntas(cog, 123, 456, "form-1")
        self.assertEqual(len(modal.children), 5)
        self.assertTrue(modal.children[0].required)
        self.assertTrue(all(not campo.required for campo in modal.children[1:]))

    def test_modais_de_avaliacao_e_decisao_respeitam_limites_do_discord(self):
        avaliacao = cog_formularios.ModalAvaliacaoFormulario("resp-123")
        decisao = cog_formularios.ModalDecisaoFormulario("resp-123", aprovado=True)

        self.assertEqual(len(avaliacao.children), 2)
        self.assertTrue(all(len(campo.label) <= 45 for campo in avaliacao.children))
        self.assertEqual(len(decisao.children), 1)
        self.assertTrue(all(len(campo.label) <= 45 for campo in decisao.children))

    def test_fila_de_candidaturas_tem_paginacao_no_limite_do_discord(self):
        central = SimpleNamespace(usuario_id=456, formulario_id="form-1")
        pendentes = [
            {"id": f"resp-{i}", "nome": f"Candidato {i}", "autor_id": i, "criado_em": i}
            for i in range(26)
        ]

        view = cog_formularios.FilaCandidaturasView(central, pendentes)

        self.assertEqual(view.total_paginas, 2)
        self.assertEqual(len(view.children[0].options), 25)
        self.assertTrue(view.anterior.disabled)
        self.assertFalse(view.proxima.disabled)

        view.pagina = 1
        view._montar()

        self.assertEqual(len(view.children[0].options), 1)
        self.assertFalse(view.anterior.disabled)
        self.assertTrue(view.proxima.disabled)

    async def test_avaliacao_estruturada_e_anexada_sem_apagar_historico(self):
        resposta = {"id": "resp-1", "status": "pendente", "avaliacoes": []}
        dados = {"123": [resposta]}
        with patch.object(storage_formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            storage_formularios, "_salvar_respostas_guild", new=AsyncMock()
        ):
            avaliacao = await storage_formularios.registrar_avaliacao(
                123,
                "resp-1",
                456,
                {
                    "postura": 5,
                    "responsabilidade": 4,
                    "disponibilidade": 3,
                    "imparcialidade": 5,
                    "comunicacao": 4,
                },
                "Boa postura e respostas consistentes.",
            )

        self.assertEqual(avaliacao["media"], 4.2)
        self.assertEqual(len(resposta["avaliacoes"]), 1)
        self.assertEqual(resposta["avaliacoes"][0]["revisor_id"], 456)

    async def test_avaliacao_nao_e_registrada_para_candidatura_encerrada(self):
        resposta = {"id": "resp-2", "status": "aprovada"}
        dados = {"123": [resposta]}
        with patch.object(storage_formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            storage_formularios, "_salvar_respostas_guild", new=AsyncMock()
        ) as salvar_respostas:
            resultado = await storage_formularios.registrar_avaliacao(
                123, "resp-2", 456,
                {"postura": 5, "responsabilidade": 5, "disponibilidade": 5, "imparcialidade": 5, "comunicacao": 5},
                "Avaliação tardia",
            )

        self.assertIsNone(resultado)
        salvar_respostas.assert_not_awaited()

    async def test_decisao_mantem_historico_com_revisor_e_data(self):
        resposta = {"id": "resp-3", "status": "pendente", "avaliacoes": [{"media": 4.0}]}
        dados = {"123": [resposta]}
        with patch.object(storage_formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            storage_formularios, "_salvar_respostas_guild", new=AsyncMock()
        ):
            resultado = await storage_formularios.definir_status_resposta(
                123, "resp-3", "aprovada", 789, "Avaliação concluída."
            )

        self.assertEqual(resultado["historico_decisoes"][0]["status"], "aprovada")
        self.assertEqual(resultado["historico_decisoes"][0]["revisor_id"], 789)
        self.assertEqual(resultado["historico_decisoes"][0]["motivo"], "Avaliação concluída.")
        self.assertGreater(resultado["historico_decisoes"][0]["criado_em"], 0)

    def test_candidatura_longa_respeita_limite_de_campos_por_embed(self):
        perguntas = [
            {"id": str(i), "texto": f"Pergunta {i}", "tipo": "longa"}
            for i in range(61)
        ]
        formulario = {
            "nome": "Teste",
            "paginas": [{"titulo": "Etapa", "perguntas": perguntas}],
        }
        resposta = {
            "id": "resposta-teste",
            "autor_id": 123456789,
            "respostas": [f"Resposta {i}" for i in range(61)],
        }
        guild = SimpleNamespace(name="NÊMESIS")

        embeds = _embeds_resposta(formulario, resposta, guild)

        self.assertEqual(len(embeds), 4)
        self.assertTrue(all(len(embed.fields) <= 25 for embed in embeds))
        self.assertEqual(
            sum(len(embed.fields) for embed in embeds),
            61,
        )


class TestFormulariosConfiguracaoInterativa(unittest.TestCase):
    def test_modal_de_candidatura_renderiza_escolha_com_select_nativo(self):
        modal = cog_formularios.ModalFormulario({
            "id": "form-escolha",
            "nome": "Recrutamento",
            "paginas": [{
                "titulo": "Perfil",
                "perguntas": [{
                    "texto": "Qual divisão prefere?",
                    "tipo": "escolha",
                    "obrigatoria": False,
                    "opcoes": ["Alpha", "Vanguard", "Recon"],
                }],
            }],
        }, usuario_id=456)

        self.assertEqual(len(modal.children), 1)
        campo = modal.children[0]
        self.assertIsInstance(campo, discord.ui.Label)
        self.assertIsInstance(campo.component, discord.ui.Select)
        self.assertFalse(campo.component.required)
        self.assertEqual(campo.component.min_values, 0)
        self.assertEqual([opcao.value for opcao in campo.component.options], ["Alpha", "Vanguard", "Recon"])
        self.assertIn("Perfil", modal.title)

    def test_modal_de_edicao_expoe_tipo_obrigatoriedade_e_opcoes(self):
        modal = cog_formularios.ModalEditarPergunta(
            object(), 123, 456, "form-1", 0,
            "Qual divisão?", "escolha", False, ["Alpha", "Recon"],
        )

        self.assertEqual(len(modal.children), 4)
        self.assertTrue(all(isinstance(item, discord.ui.Label) for item in modal.children))
        self.assertEqual([opcao.value for opcao in modal.tipo.options], ["texto", "paragrafo", "escolha"])
        self.assertEqual([opcao.value for opcao in modal.obrigatoria.options], ["sim", "nao"])
        self.assertEqual(modal.opcoes.default, "Alpha\nRecon")

    def test_central_de_formularios_oferece_renomear_etapa(self):
        central = SimpleNamespace(cog=object(), usuario_id=456, guild_id=123, formulario_id="form-1")
        seletor = cog_formularios.SeletorAcaoFormulario(central)
        self.assertIn("editar_etapa", {opcao.value for opcao in seletor.options})

    def test_seletor_de_etapas_expoe_titulos_atuais(self):
        seletor = cog_formularios.SeletorPaginaEditar(
            object(), 123, 456,
            {"id": "form-1", "paginas": [{"titulo": "Informações pessoais", "perguntas": ["Nome"]}]},
        )
        self.assertEqual(len(seletor.options), 1)
        self.assertIn("Informações pessoais", seletor.options[0].label)


if __name__ == "__main__":
    unittest.main()
