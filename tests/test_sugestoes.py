import unittest
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

    def test_painel_administrativo_exibe_contagens_e_populares(self):
        registros = {
            "101": {"id": 101, "titulo": "Sistema novo", "status": "pendente", "votos": {"1": "apoia"}},
            "102": {"id": 102, "titulo": "Evento", "status": "implementada", "votos": {"1": "apoia", "2": "apoia"}},
        }
        embed = _embed_painel_administrativo(registros, "populares")
        self.assertIn("2", embed.fields[0].value)
        self.assertIn("Evento", embed.fields[-1].value)


class TestOperacoesAssincronasSugestoes(unittest.IsolatedAsyncioTestCase):

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
        self.assertEqual(mensagem.edit.await_args.kwargs["embed"].title, "💡 Sugestão antiga")
        self.assertEqual(len(mensagem.edit.await_args.kwargs["view"].children), 6)

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
            components=[SimpleNamespace(children=[SimpleNamespace(custom_id=item) for item in ids_atuais])],
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

