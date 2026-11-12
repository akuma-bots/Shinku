import unittest

from utils.historico_membros import filtrar_revisoes_membro, _resumo_revisoes


class TestHistoricoMembros(unittest.TestCase):
    def test_inclui_autor_e_auxiliar_sem_duplicar_protocolo(self):
        registros = [
            {"id": "a", "autor_id": 10, "auxiliar_id": 20, "status": "aprovada", "tipo": "missao", "timestamp": 100},
            {"id": "b", "autor_id": 30, "auxiliar_id": 10, "status": "pendente", "tipo": "pvp", "timestamp": 200},
            {"id": "c", "autor_id": 40, "auxiliar_id": None, "status": "rejeitada", "tipo": "contribuicao", "timestamp": 300},
            {"id": "b", "autor_id": 10, "auxiliar_id": None, "status": "aprovada", "tipo": "pvp", "timestamp": 250},
        ]
        resultado = filtrar_revisoes_membro(registros, 10)
        self.assertEqual([item["id"] for item in resultado], ["b", "a"])

    def test_resumo_separa_status_e_categoria(self):
        resumo = _resumo_revisoes([
            {"status": "aprovada", "tipo": "missao"},
            {"status": "aprovada", "tipo": "missao"},
            {"status": "pendente", "tipo": "pvp"},
            {"status": "rejeitada", "tipo": "contribuicao"},
        ])
        self.assertEqual(resumo["total"], 4)
        self.assertEqual(resumo["aprovadas"], 2)
        self.assertEqual(resumo["pendentes"], 1)
        self.assertEqual(resumo["rejeitadas"], 1)
        self.assertEqual(resumo["por_tipo"]["missao"], 2)

    def test_ignora_registros_invalidos_e_nao_correlacionados(self):
        resultado = filtrar_revisoes_membro([None, "invalido", {"id": "x", "autor_id": 99}], 10)
        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()

class TestHistoricoEmbeds(unittest.TestCase):
    def test_linha_do_tempo_respeita_limite_de_campos_discord(self):
        from utils.historico_membros import _embed_registros

        eventos = [
            {
                "categoria": "historico_membros",
                "titulo": f"Evento {i}",
                "descricao": "Detalhes do evento " * 20,
                "timestamp": 1_700_000_000 + i,
                "url": f"https://discord.com/channels/1/2/{i}",
            }
            for i in range(18)
        ]
        embed = _embed_registros({"eventos": eventos})
        self.assertTrue(embed.fields)
        self.assertTrue(all(len(campo.value) <= 1024 for campo in embed.fields))
        self.assertLessEqual(len(embed.fields), 25)


class TestPainelHistoricoRegistro(unittest.TestCase):
    def test_painel_persistente_sem_comando_slash(self):
        from cogs.logs import PainelHistoricoMembrosView, SeletorMembroRegistroView
        from utils import historico_membros

        painel = PainelHistoricoMembrosView()
        seletor = SeletorMembroRegistroView(123)
        self.assertIsNone(painel.timeout)
        self.assertEqual(painel.children[0].custom_id, "nemesis:registro:membro:abrir")
        self.assertEqual(seletor.children[0].custom_id, "nemesis:registro:membro:selecionar")
        from cogs.logs import DossieMembroRegistroView
        dossie = DossieMembroRegistroView({"guild": None, "membro": None}, 123)
        rotulos = {getattr(item, "label", None) for item in dossie.children}
        self.assertIn("Atualizar dados", rotulos)
        self.assertNotIn("Anterior", rotulos)
        self.assertNotIn("Próxima", rotulos)
        self.assertFalse(hasattr(historico_membros, "HistoricoMembros"))


class TestTimeoutCompatibilidade(unittest.TestCase):
    def test_usa_atributo_timed_out_until_do_discord_py(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        data = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.assertEqual(_timeout_membro(SimpleNamespace(timed_out_until=data)), data)

    def test_fallback_para_forks_com_communication_disabled_until(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        data = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.assertEqual(_timeout_membro(SimpleNamespace(communication_disabled_until=data)), data)

    def test_membro_sem_timeout(self):
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        self.assertIsNone(_timeout_membro(SimpleNamespace()))


class TestEscopoHistoricoMembros(unittest.TestCase):
    def test_nao_consulta_mensagens_cargos_ou_conquistas_no_arquivo(self):
        from utils.historico_membros import CATEGORIAS_HISTORICO, ABAS
        self.assertNotIn("mensagens", CATEGORIAS_HISTORICO)
        self.assertNotIn("mensagens", {chave for chave, *_ in ABAS})
        self.assertNotIn("administracao", CATEGORIAS_HISTORICO)
        self.assertNotIn("eventos", CATEGORIAS_HISTORICO)
        self.assertNotIn("conquistas", {chave for chave, *_ in ABAS})

    def test_visao_geral_nao_exibe_cargos_ou_conquistas(self):
        from types import SimpleNamespace
        from utils.historico_membros import _embed_geral
        membro = SimpleNamespace(
            display_name="Membro", name="membro", id=123,
            created_at=__import__("datetime").datetime(2026, 1, 1),
            display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
            bot=False,
        )
        dados = {
            "membro": membro, "perfil": {}, "progressao": {},
            "perfil_competitivo": {}, "resumo_missoes": {
                "total": 0, "aprovadas": 0, "pendentes": 0,
                "rejeitadas": 0, "por_tipo": {},
            },
            "guild": SimpleNamespace(), "membro_presente": False,
            "punicoes": [], "eventos": [], "convidador_id": None,
            "convidados_ativos": [], "conquistas": {},
        }
        embed = _embed_geral(dados)
        texto = " ".join([embed.description or ""] + [f.name + " " + f.value for f in embed.fields])
        self.assertNotIn("CARGOS ATUAIS", texto)
        self.assertNotIn("Conquistas", texto)


class TestMensagensEMonitoramento(unittest.TestCase):
    def test_embed_mensagens_mostra_status_e_versao_anterior(self):
        from utils.historico_membros import _embed_mensagens
        dados = {"atividade": {"mensagens": [{
            "message_id": "123", "canal_id": 456, "timestamp": 1_700_000_000,
            "conteudo": "texto atual", "status": "excluida",
            "excluida_em": 1_700_000_100,
            "revisoes": [{"conteudo": "texto anterior", "timestamp": 1_700_000_050}],
            "anexos": [],
        }]}}
        embed = _embed_mensagens(dados)
        texto = " ".join([embed.description or ""] + [f"{f.name} {f.value}" for f in embed.fields])
        self.assertIn("EXCLUÍDA", texto)
        self.assertIn("texto atual", texto)
        self.assertIn("texto anterior", texto)

    def test_abas_separam_monitoramento_de_mensagens(self):
        from utils.historico_membros import ABAS
        chaves = {chave for chave, *_ in ABAS}
        self.assertNotIn("mensagens", chaves)
        self.assertIn("atividade", chaves)
        self.assertNotIn("conquistas", chaves)
        self.assertNotIn("cargos", chaves)


class TestPersistenciaMonitoramento(unittest.IsolatedAsyncioTestCase):
    async def test_mensagem_editada_e_excluida_preserva_conteudo_e_revisao(self):
        from unittest.mock import patch, AsyncMock
        from utils import monitoramento_membros as monitor
        estado = {}

        async def atualizar(nome, padrao, transformador):
            atual = estado.get(nome, padrao)
            estado[nome] = transformador(atual)
            return estado[nome]

        with patch.object(monitor, "atualizar_json", new=AsyncMock(side_effect=atualizar)), patch.object(monitor, "salvar_com_expiracao", new=AsyncMock()):
            await monitor.registrar_mensagem(1, 2, {
                "message_id": "99", "canal_id": 3, "timestamp": 1_800_000_000,
                "conteudo": "original", "status": "enviada",
            })
            await monitor.registrar_mensagem(1, 2, {
                "message_id": "99", "canal_id": 3, "timestamp": 1_800_000_000,
                "conteudo": "editada", "status": "editada",
            })
            await monitor.registrar_mensagem(1, 2, {
                "message_id": "99", "canal_id": 3, "timestamp": 1_800_000_000,
                "conteudo": "editada", "status": "excluida", "excluida_em": 1_800_000_100,
            })
        item = estado[monitor._arquivo(1, 2)]["mensagens"][0]
        self.assertEqual(item["conteudo"], "editada")
        self.assertEqual(item["status"], "excluida")
        self.assertEqual(item["revisoes"][0]["conteudo"], "original")
        self.assertEqual(item["excluida_em"], 1_800_000_100)

    async def test_eventos_sao_deduplicados(self):
        from unittest.mock import patch, AsyncMock
        from utils import monitoramento_membros as monitor
        estado = {}

        async def atualizar(nome, padrao, transformador):
            atual = estado.get(nome, padrao)
            estado[nome] = transformador(atual)
            return estado[nome]

        with patch.object(monitor, "atualizar_json", new=AsyncMock(side_effect=atualizar)), patch.object(monitor, "definir_expiracao", new=AsyncMock()):
            await monitor.registrar_evento(1, 2, "voz_entrada", "Entrou", timestamp=1_800_000_000)
            await monitor.registrar_evento(1, 2, "voz_entrada", "Entrou", timestamp=1_800_000_000)
        self.assertEqual(len(estado[monitor._arquivo(1, 2)]["eventos"]), 1)


class TestMonitoramentoAmpliado(unittest.IsolatedAsyncioTestCase):
    async def test_exclusao_em_massa_vai_apenas_para_dossie_privado(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from cogs.logs import Logs, GUILD_NEMESIS_ID

        mensagem = SimpleNamespace(
            guild=SimpleNamespace(id=GUILD_NEMESIS_ID),
            author=SimpleNamespace(id=321, bot=False),
            id=654, channel=SimpleNamespace(id=987),
            created_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
            content="conteúdo removido", jump_url="https://discord.com/channels/1/2/3",
            attachments=[],
        )
        cog = object.__new__(Logs)
        with patch("cogs.logs.monitoramento_membros.registrar_mensagem", new=AsyncMock()) as registrar, patch.object(
            cog, "_canal_logs", new=AsyncMock()
        ) as publicar:
            await cog.on_bulk_message_delete([mensagem])

        registrar.assert_awaited_once()
        dados = registrar.await_args.args[2]
        self.assertEqual(dados["status"], "excluida")
        self.assertEqual(dados["conteudo"], "conteúdo removido")
        publicar.assert_not_awaited()

    async def test_presenca_e_jogo_sao_registrados_sem_status_personalizado(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        import discord
        from cogs.logs import Logs, GUILD_NEMESIS_ID

        antes = SimpleNamespace(
            guild=SimpleNamespace(id=GUILD_NEMESIS_ID), id=123, bot=False,
            status=discord.Status.online,
            activities=[SimpleNamespace(type=discord.ActivityType.playing, name="GTA V")],
        )
        depois = SimpleNamespace(
            guild=SimpleNamespace(id=GUILD_NEMESIS_ID), id=123, bot=False,
            status=discord.Status.dnd,
            activities=[SimpleNamespace(type=discord.ActivityType.playing, name="Valorant")],
        )
        cog = object.__new__(Logs)
        with patch("cogs.logs.monitoramento_membros.registrar_evento", new=AsyncMock()) as registrar:
            await cog.on_presence_update(antes, depois)

        registrar.assert_awaited_once()
        self.assertEqual(registrar.await_args.args[2], "presenca")
        self.assertIn("online → dnd", registrar.await_args.args[3])
        self.assertIn("GTA V", registrar.await_args.args[3])
        self.assertIn("Valorant", registrar.await_args.args[3])


    async def test_mudanca_de_cargo_nao_cria_historico_separado(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from cogs.logs import Logs, GUILD_NEMESIS_ID

        guild = SimpleNamespace(id=GUILD_NEMESIS_ID)
        cargo_antigo = SimpleNamespace(id=10, name="Membro", is_default=lambda: False)
        cargo_novo = SimpleNamespace(id=11, name="Supervisor", is_default=lambda: False)
        antes = SimpleNamespace(
            guild=guild, id=123, roles=[cargo_antigo], nick=None, name="membro",
            global_name="Membro", premium_since=None,
        )
        depois = SimpleNamespace(
            guild=guild, id=123, roles=[cargo_antigo, cargo_novo], nick=None, name="membro",
            global_name="Membro", premium_since=None,
        )
        cog = object.__new__(Logs)
        with patch("cogs.logs.monitoramento_membros.registrar_evento", new=AsyncMock()) as registrar, patch.object(
            cog, "_canal_logs", new=AsyncMock(return_value=None)
        ):
            await cog.on_member_update(antes, depois)

        # O Arquivo de Membros não mantém uma trilha separada de cargos.
        registrar.assert_not_awaited()


class TestCartaoHistoricoComponentsV2(unittest.IsolatedAsyncioTestCase):
    async def test_dossie_extenso_preserva_todo_o_texto_e_aninha_controles(self):
        from unittest.mock import AsyncMock
        import discord
        from cogs.logs import _card_registro

        origem = discord.ui.View(timeout=90)
        callback_aba = AsyncMock()
        callback_usuario = AsyncMock()
        callback_atualizar = AsyncMock()

        seletor_aba = discord.ui.Select(
            placeholder="Escolha uma seção",
            options=[discord.SelectOption(label="Geral", value="geral")],
            custom_id="nemesis:registro:membro:aba",
            row=0,
        )
        seletor_aba.callback = callback_aba
        seletor_usuario = discord.ui.UserSelect(
            placeholder="Selecione um membro",
            custom_id="nemesis:registro:membro:selecionar",
            row=1,
        )
        seletor_usuario.callback = callback_usuario
        botao = discord.ui.Button(
            label="Atualizar dados",
            custom_id="nemesis:registro:membro:atualizar",
            row=2,
        )
        botao.callback = callback_atualizar

        origem.add_item(seletor_aba)
        origem.add_item(seletor_usuario)
        origem.add_item(botao)
        verificacao = AsyncMock(return_value=True)
        origem.interaction_check = verificacao

        embed = discord.Embed(
            title="Dossiê individual extenso",
            description="INICIO_DOSSIE " + ("detalhes da descrição " * 180),
        )
        for indice in range(20):
            embed.add_field(
                name=f"Registro {indice:02d}",
                value=f"RESPOSTA_{indice:02d} " + ("detalhe preservado " * 45),
                inline=False,
            )
        embed.set_footer(text="FIM_DO_DOSSIE")

        cartao = _card_registro(origem, embed)

        self.assertIsInstance(cartao, discord.ui.LayoutView)
        self.assertEqual(cartao.timeout, 90)
        self.assertIs(cartao.interaction_check, verificacao)
        self.assertEqual(len(cartao.children), 1)

        container = cartao.children[0]
        self.assertIsInstance(container, discord.ui.Container)
        textos = [
            item.content for item in container.children
            if isinstance(item, discord.ui.TextDisplay)
        ]
        self.assertGreater(len(textos), 1)
        self.assertTrue(all(len(texto) <= 3900 for texto in textos))

        partes_esperadas = [f"## {embed.title}", embed.description]
        partes_esperadas.extend(
            f"**{campo.name}**\n{campo.value}" for campo in embed.fields
        )
        partes_esperadas.append(f"-# {embed.footer.text}")
        self.assertEqual("".join(textos), "\n\n".join(partes_esperadas))

        linhas = [
            item for item in container.children
            if isinstance(item, discord.ui.ActionRow)
        ]
        self.assertEqual(len(linhas), 3)
        controles = [controle for linha in linhas for controle in linha.children]
        self.assertEqual(
            {controle.custom_id for controle in controles},
            {
                "nemesis:registro:membro:aba",
                "nemesis:registro:membro:selecionar",
                "nemesis:registro:membro:atualizar",
            },
        )
        self.assertFalse(any(
            isinstance(item, (discord.ui.Button, discord.ui.Select, discord.ui.UserSelect))
            for item in container.children
        ))

        clone_aba = next(
            item for item in controles
            if item.custom_id == "nemesis:registro:membro:aba"
        )
        clone_usuario = next(
            item for item in controles
            if item.custom_id == "nemesis:registro:membro:selecionar"
        )
        clone_botao = next(
            item for item in controles
            if item.custom_id == "nemesis:registro:membro:atualizar"
        )

        interaction = object()
        clone_aba._values = ["geral"]
        await clone_aba.callback(interaction)
        callback_aba.assert_awaited_once_with(interaction)
        self.assertEqual(seletor_aba._values, ["geral"])

        clone_usuario._values = ["123456"]
        await clone_usuario.callback(interaction)
        callback_usuario.assert_awaited_once_with(interaction)
        self.assertEqual(seletor_usuario._values, ["123456"])

        self.assertIs(clone_botao.callback, callback_atualizar)
        self.assertEqual(clone_aba.options[0].value, "geral")
        self.assertLessEqual(
            1 + len(container.children) + sum(
                len(item.children) for item in container.children
                if isinstance(item, discord.ui.ActionRow)
            ),
            40,
        )
