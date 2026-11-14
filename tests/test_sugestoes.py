import unittest

import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.sugestoes import (
    CATEGORIAS,
    STATUS,
    STATUS_TERMINAIS,
    _contagem_votos,
    _normalizar_categoria,
    _normalizar_titulo,
    _encontrar_duplicada,
    _registro_no_canal,
    _registrar_voto,
    _embed_sugestao,
    _card_sugestoes_view,
    _embed_painel_administrativo,
    PainelSugestoesView,
    PublicacaoSugestaoView,
    ModalNovaSugestao,
    ModalEditarSugestao,
    _alternar_seguidor,
    _atualizar_decisao,
    _editar_registro,
    _esta_no_canal_sugestoes,
    CANAL_SUGESTOES_ID,
    GUILD_NEMESIS_ID,
    Sugestoes,
    _notificar_atualizacao_sugestao,
)


class TestSistemaSugestoes(unittest.TestCase):
    def test_categorias_oficiais_estao_disponiveis(self):
        self.assertIn("Sistemas", CATEGORIAS)
        self.assertIn("Comunidade", CATEGORIAS)
        self.assertIn("Outros", CATEGORIAS)

    def test_painel_em_thread_de_forum_e_reconhecido_como_canal_oficial(self):
        class FakeThread:
            def __init__(self, parent_id):
                self.parent_id = parent_id
                self.id = 900

        interacao = SimpleNamespace(
            guild_id=GUILD_NEMESIS_ID,
            channel=FakeThread(CANAL_SUGESTOES_ID),
        )
        with patch("cogs.sugestoes.discord.Thread", FakeThread):
            self.assertTrue(_esta_no_canal_sugestoes(interacao))

    def test_categoria_aceita_acentos_e_apelidos(self):
        self.assertEqual(_normalizar_categoria("Missões"), "Missões e operações")
        self.assertEqual(_normalizar_categoria("operacoes"), "Missões e operações")
        self.assertEqual(_normalizar_categoria("categoria desconhecida"), "Outros")

    def test_titulos_sao_normalizados_para_detectar_duplicatas(self):
        self.assertEqual(_normalizar_titulo("  NOVO Sistema!!! "), "novo sistema")
        registros = {
            "1": {"id": 1, "titulo": "Criar sistema de patentes", "status": "pendente"},
            "2": {"id": 2, "titulo": "Evento antigo", "status": "implementada"},
        }
        self.assertEqual(_encontrar_duplicada(registros, "Criar sistema de patentes")["id"], 1)
        self.assertIsNone(_encontrar_duplicada(registros, "Criar evento de verão"))
        self.assertIsNone(_encontrar_duplicada(registros, "Criar sistema de patentes", ignorar_id="1"))

    def test_publicacao_so_e_valida_no_topico_oficial(self):
        class FakeThread:
            def __init__(self, id, parent_id):
                self.id = id
                self.parent_id = parent_id

        interacao = SimpleNamespace(
            guild_id=GUILD_NEMESIS_ID,
            channel=FakeThread(901, CANAL_SUGESTOES_ID),
        )
        registro = {"canal_publicacao_id": 901}
        with patch("cogs.sugestoes.discord.Thread", FakeThread):
            self.assertTrue(_registro_no_canal(interacao, registro))
            self.assertFalse(_registro_no_canal(interacao, {"canal_publicacao_id": 902}))

    def test_publicacao_em_forum_aceita_id_do_topico_ou_do_forum(self):
        class FakeThread:
            def __init__(self, id, parent_id):
                self.id = id
                self.parent_id = parent_id
        interacao = SimpleNamespace(guild_id=GUILD_NEMESIS_ID, channel=FakeThread(901, CANAL_SUGESTOES_ID))
        with patch("cogs.sugestoes.discord.Thread", FakeThread):
            self.assertTrue(_registro_no_canal(interacao, {"canal_publicacao_id": 901}))
            self.assertTrue(_registro_no_canal(interacao, {"canal_publicacao_id": CANAL_SUGESTOES_ID}))
            self.assertFalse(_registro_no_canal(interacao, {"canal_publicacao_id": 902}))

    def test_voto_unico_pode_ser_alterado_ou_removido(self):
        votos = _registrar_voto({}, 10, "apoia")
        self.assertEqual(votos, {"10": "apoia"})
        votos = _registrar_voto(votos, 10, "nao_apoia")
        self.assertEqual(votos, {"10": "nao_apoia"})
        votos = _registrar_voto(votos, 10, "nao_apoia")
        self.assertEqual(votos, {})

    def test_contagem_e_percentual_refletem_votos(self):
        votos = {"1": "apoia", "2": "apoia", "3": "nao_apoia"}
        self.assertEqual(_contagem_votos(votos), (2, 1))
        registro = {
            "id": 123, "titulo": "Ideia", "descricao": "Descrição",
            "autor_id": 1, "categoria": "Sistemas", "status": "pendente",
            "votos": votos,
            "impacto": "Melhorar a organização da equipe.",
        }
        embed = _embed_sugestao(registro)
        self.assertIn("67%", embed.fields[6].value)
        self.assertIn("Melhorar a organização", embed.fields[3].value)

    def test_status_terminais_encerram_votacao(self):
        self.assertEqual(STATUS_TERMINAIS, {"rejeitada", "implementada"})
        self.assertIn("aprovada", STATUS)
        self.assertIn("analise", STATUS)

    def test_formularios_capturam_contexto_e_resultado_esperado(self):
        novo = ModalNovaSugestao()
        editar = ModalEditarSugestao("123", {
            "titulo": "Título original",
            "descricao": "Descrição original da proposta",
            "impacto": "Resultado esperado da proposta",
        })
        self.assertEqual(len(novo.children), 4)
        self.assertEqual(len(editar.children), 3)
        self.assertEqual(editar.titulo.default, "Título original")

    def test_paineis_publicos_sao_persistentes_e_nao_criam_comandos(self):
        painel = PainelSugestoesView()
        publicacao = PublicacaoSugestaoView()
        self.assertIsNone(painel.timeout)
        self.assertIsNone(publicacao.timeout)
        self.assertEqual(len(painel.children), 2)
        self.assertEqual(len(publicacao.children), 6)
        self.assertTrue(all(item.custom_id for item in painel.children + publicacao.children))
        encerrada = PublicacaoSugestaoView(votacao_encerrada=True, edicao_encerrada=True)
        botoes = {item.custom_id: item for item in encerrada.children}
        self.assertTrue(botoes["nemesis:sugestoes:votar:apoia"].disabled)
        self.assertTrue(botoes["nemesis:sugestoes:editar"].disabled)
        self.assertFalse(botoes["nemesis:sugestoes:acompanhar"].disabled)

    def test_cartao_v2_preserva_texto_longo_e_aninha_todos_os_controles(self):
        linhas = [f"PASSO-{indice:03d} " + ("instrução " * 24) for indice in range(120)]
        descricao = "\n".join(linhas)
        embed = discord.Embed(title="Sugestão extensa", description=descricao)
        origem = PublicacaoSugestaoView()
        cartao = _card_sugestoes_view(origem, embed)

        self.assertTrue(all(isinstance(item, discord.ui.Container) for item in cartao.children))
        containers = list(cartao.children)
        componentes = []

        def percorrer(item):
            componentes.append(item)
            for filho in getattr(item, "children", []) or []:
                percorrer(filho)

        for container in containers:
            percorrer(container)

        textos = [item.content for item in componentes if isinstance(item, discord.ui.TextDisplay)]
        self.assertGreater(len(textos), 1)
        self.assertIn("PASSO-119", "".join(textos))
        self.assertTrue(all(len(texto) <= 4000 for texto in textos))

        linhas_controle = [
            item for item in componentes if isinstance(item, discord.ui.ActionRow)
        ]
        self.assertGreaterEqual(len(linhas_controle), 2)
        self.assertTrue(all(linha.children for linha in linhas_controle))
        controles = [
            filho
            for linha in linhas_controle
            for filho in linha.children
        ]
        self.assertEqual(
            {item.custom_id for item in controles},
            {
                "nemesis:sugestoes:votar:apoia",
                "nemesis:sugestoes:votar:nao_apoia",
                "nemesis:sugestoes:comentar",
                "nemesis:sugestoes:acompanhar",
                "nemesis:sugestoes:editar",
                "nemesis:sugestoes:gerenciar",
            },
        )
        self.assertTrue(all(callable(item.callback) for item in controles))

    def test_painel_administrativo_nao_corta_lista_de_dez_sugestoes(self):
        registros = {
            str(indice): {
                "id": indice,
                "titulo": f"Sugestão {indice:02d} " + ("x" * 75),
                "status": "pendente",
                "criado_em": f"2026-11-{indice:02d}T00:00:00+00:00",
                "canal_publicacao_id": CANAL_SUGESTOES_ID,
                "votos": {"1": "apoia", "2": "nao_apoia"},
            }
            for indice in range(1, 11)
        }
        embed = _embed_painel_administrativo(registros, "resumo")
        campos = [
            campo for campo in embed.fields
            if campo.name.startswith("🕒 ATIVIDADE RECENTE")
        ]
        conteudo = "\n".join(campo.value for campo in campos)

        self.assertGreater(len(campos), 1)
        self.assertTrue(all(len(campo.value) <= 1024 for campo in campos))
        for indice in range(1, 11):
            self.assertIn(f"Sugestão {indice:02d}", conteudo)

    def test_painel_administrativo_exibe_contagens_e_populares(self):
        registros = {
            "101": {"id": 101, "titulo": "Sistema novo", "status": "pendente", "votos": {"1": "apoia"}},
            "102": {"id": 102, "titulo": "Evento", "status": "implementada", "votos": {"1": "apoia", "2": "apoia"}},
        }
        embed = _embed_painel_administrativo(registros, "populares")
        self.assertIn("2", embed.fields[0].value)
        self.assertIn("Evento", embed.fields[-1].value)


class TestOperacoesAssincronasSugestoes(unittest.IsolatedAsyncioTestCase):

    async def test_voto_responde_privadamente_e_edita_publicacao(self):
        mensagem = SimpleNamespace(id=321, edit=AsyncMock())
        interaction = SimpleNamespace(
            message=mensagem, user=SimpleNamespace(id=22, bot=False),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        registro = {
            "id": 321, "autor_id": 11, "status": "pendente",
            "titulo": "Melhoria de painel", "descricao": "Descrição válida",
            "categoria": "Sistemas", "votos": {"22": "apoia"},
        }
        with patch("cogs.sugestoes._obter_registro", AsyncMock(return_value=registro)), patch(
            "cogs.sugestoes._registro_no_canal", return_value=True
        ), patch("cogs.sugestoes._atualizar_voto", AsyncMock(return_value=registro)):
            await PublicacaoSugestaoView()._votar(interaction, "apoia")
        interaction.response.defer.assert_awaited_once()
        mensagem.edit.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_notificacao_dm_alcanca_autor_e_seguidores_sem_duplicar(self):
        autor = SimpleNamespace(send=AsyncMock())
        seguidor = SimpleNamespace(send=AsyncMock())
        guild = SimpleNamespace(get_member=lambda member_id: {10: autor, 20: seguidor}.get(member_id))
        with patch("cogs.sugestoes._listar_seguidores", AsyncMock(return_value=[20, 10, 20])):
            enviados, falhas = await _notificar_atualizacao_sugestao(
                guild, {"autor_id": 10, "titulo": "Nova função"}, "321", "analise", "A equipe iniciou a avaliação."
            )
        self.assertEqual((enviados, falhas), (2, 0))
        autor.send.assert_awaited_once()
        seguidor.send.assert_awaited_once()

    async def test_falha_de_dm_nao_interrompe_notificacao_dos_demais(self):
        bloqueou = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("DM indisponível")))
        membro_ok = SimpleNamespace(send=AsyncMock())
        guild = SimpleNamespace(get_member=lambda member_id: {10: bloqueou, 20: membro_ok}.get(member_id))
        with patch("cogs.sugestoes._listar_seguidores", AsyncMock(return_value=[20])):
            enviados, falhas = await _notificar_atualizacao_sugestao(
                guild, {"autor_id": 10, "titulo": "Nova função"}, "321", "aprovada", "Aprovada para execução."
            )
        self.assertEqual((enviados, falhas), (1, 1))
        membro_ok.send.assert_awaited_once()

    async def test_migracao_atualiza_publicacao_antiga_sem_criar_outra(self):
        ids_antigos = ["nemesis:sugestoes:votar:apoia", "nemesis:sugestoes:votar:nao_apoia"]
        mensagem = SimpleNamespace(
            components=[SimpleNamespace(children=[SimpleNamespace(custom_id=item) for item in ids_antigos])],
            edit=AsyncMock(),
        )
        canal = SimpleNamespace(fetch_message=AsyncMock(return_value=mensagem))
        guild = SimpleNamespace(
            get_channel=lambda _id: canal,
            get_thread=lambda _id: None,
            fetch_channel=AsyncMock(),
        )
        bot = SimpleNamespace(add_view=lambda _view: None)
        cog = Sugestoes(bot)
        registro = {
            "id": 321,
            "canal_publicacao_id": 654,
            "titulo": "Sugestão antiga",
            "status": "pendente",
            "criado_em": "2026-11-01T00:00:00+00:00",
        }
        with patch("cogs.sugestoes.carregar", AsyncMock(return_value={"321": registro})):
            total = await cog._sincronizar_publicacoes_existentes(guild)
        self.assertEqual(total, 1)
        mensagem.edit.assert_awaited_once()
        view = mensagem.edit.await_args.kwargs["view"]
        controles = []
        pendentes = list(view.children)
        while pendentes:
            componente = pendentes.pop()
            custom_id = getattr(componente, "custom_id", None)
            if custom_id:
                controles.append(custom_id)
            pendentes.extend(list(getattr(componente, "children", []) or []))
        self.assertEqual(set(controles), {
            "nemesis:sugestoes:votar:apoia",
            "nemesis:sugestoes:votar:nao_apoia",
            "nemesis:sugestoes:comentar",
            "nemesis:sugestoes:acompanhar",
            "nemesis:sugestoes:editar",
            "nemesis:sugestoes:gerenciar",
        })

    async def test_migracao_recupera_topico_do_forum_quando_id_salvo_esta_obsoleto(self):
        class FakeThread:
            def __init__(self):
                self.id = 321
                self.parent_id = 654
                self.fetch_message = AsyncMock(return_value=SimpleNamespace(
                    components=[SimpleNamespace(children=[])], edit=AsyncMock()
                ))
        class FakeForum:
            def __init__(self):
                self.id = 654
                self.archived_threads = AsyncMock()
        forum, thread = FakeForum(), FakeThread()
        guild = SimpleNamespace(
            get_channel=lambda channel_id: forum if channel_id == 654 else None,
            get_thread=lambda thread_id: thread if thread_id == 321 else None,
            fetch_channel=AsyncMock(return_value=None),
        )
        cog = Sugestoes(SimpleNamespace(add_view=lambda _view: None))
        registro = {
            "id": 321, "canal_publicacao_id": 999, "status": "pendente",
            "titulo": "Sugestão antiga", "descricao": "Descrição preservada",
            "autor_id": 11, "categoria": "Sistemas", "votos": {},
        }
        with patch("cogs.sugestoes.CANAL_SUGESTOES_ID", 654), patch(
            "cogs.sugestoes.discord.ForumChannel", FakeForum
        ), patch("cogs.sugestoes.discord.Thread", FakeThread), patch(
            "cogs.sugestoes.carregar", AsyncMock(return_value={"321": registro})
        ):
            total = await cog._sincronizar_publicacoes_existentes(guild)
        self.assertEqual(total, 1)
        thread.fetch_message.assert_awaited_once_with(321)

    async def test_migracao_nao_edita_publicacao_que_ja_tem_todos_os_botoes(self):
        ids_atuais = [
            "nemesis:sugestoes:votar:apoia",
            "nemesis:sugestoes:votar:nao_apoia",
            "nemesis:sugestoes:comentar",
            "nemesis:sugestoes:acompanhar",
            "nemesis:sugestoes:editar",
            "nemesis:sugestoes:gerenciar",
        ]
        mensagem = SimpleNamespace(
            components=[SimpleNamespace(
                content="-# NÊMESIS • PUBLICAÇÃO DE SUGESTÃO • V2",
                children=[SimpleNamespace(custom_id=item) for item in ids_atuais],
            )],
            edit=AsyncMock(),
        )
        canal = SimpleNamespace(fetch_message=AsyncMock(return_value=mensagem))
        guild = SimpleNamespace(
            get_channel=lambda _id: canal,
            get_thread=lambda _id: None,
            fetch_channel=AsyncMock(),
        )
        cog = Sugestoes(SimpleNamespace(add_view=lambda _view: None))
        registro = {"id": 322, "canal_publicacao_id": 654, "status": "pendente"}
        with patch("cogs.sugestoes.carregar", AsyncMock(return_value={"322": registro})):
            total = await cog._sincronizar_publicacoes_existentes(guild)
        self.assertEqual(total, 0)
        mensagem.edit.assert_not_awaited()

    async def test_seguidor_pode_ativar_e_desativar_acompanhamento(self):
        dados = {}
        async def fake_atualizar(nome, padrao, transformador):
            nonlocal dados
            dados = transformador(dados)
        with patch("cogs.sugestoes.atualizar_json", fake_atualizar):
            self.assertTrue(await _alternar_seguidor("100", 55))
            self.assertEqual(dados["100"], ["55"])
            self.assertFalse(await _alternar_seguidor("100", 55))
            self.assertEqual(dados["100"], [])

    async def test_decisao_registra_trilha_de_auditoria(self):
        dados = {
            "100": {
                "id": 100,
                "status": "pendente",
                "titulo": "Sugestão",
                "historico_status": [],
            }
        }
        async def fake_atualizar(nome, padrao, transformador):
            nonlocal dados
            dados = transformador(dados)
        with patch("cogs.sugestoes.atualizar_json", fake_atualizar):
            resultado = await _atualizar_decisao("100", "desenvolvimento", "Equipe iniciou o trabalho", 77)
        self.assertEqual(resultado["status"], "desenvolvimento")
        self.assertEqual(resultado["historico_status"][-1]["de"], "pendente")
        self.assertEqual(resultado["historico_status"][-1]["responsavel_id"], 77)

    async def test_edicao_so_permite_autor_e_status_aberto(self):
        dados = {
            "100": {"id": 100, "autor_id": 55, "status": "pendente", "titulo": "Antes"}
        }
        async def fake_atualizar(nome, padrao, transformador):
            nonlocal dados
            dados = transformador(dados)
        with patch("cogs.sugestoes.atualizar_json", fake_atualizar):
            self.assertIsNone(await _editar_registro("100", 99, "Depois", "Descrição suficiente", "Impacto esperado"))
            self.assertIsNotNone(await _editar_registro("100", 55, "Depois", "Descrição suficiente", "Impacto esperado"))
            dados["100"]["status"] = "implementada"
            self.assertIsNone(await _editar_registro("100", 55, "Terceira", "Outra descrição suficiente", "Outro impacto esperado"))


if __name__ == "__main__":
    unittest.main()

