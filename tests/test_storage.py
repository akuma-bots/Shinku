import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import storage


class TestStorageLocal(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_dir = Path(self.tempdir.name)
        self.patch_dir = patch.object(storage, "DATA_DIR", self.data_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

    def test_rejeita_caminho_fora_do_diretorio_de_dados(self):
        for nome in ("../segredo.json", "/tmp/segredo.json", "subpasta/arquivo.json"):
            with self.subTest(nome=nome):
                with self.assertRaises(storage.ErroStorage):
                    storage._path(nome)

    def test_salvamento_atomico_preserva_json_valido(self):
        destino = storage._path("estado.json")
        storage._salvar_local("estado.json", {"membros": [1, 2, 3]})

        self.assertEqual(json.loads(destino.read_text(encoding="utf-8")), {"membros": [1, 2, 3]})
        self.assertEqual(list(self.data_dir.glob("*.tmp")), [])

    def test_arquivo_ausente_recebe_padrao(self):
        resultado = storage._carregar_local("novo.json", {"ativo": True})
        self.assertEqual(resultado, {"ativo": True})
        self.assertEqual(json.loads((self.data_dir / "novo.json").read_text(encoding="utf-8")), {"ativo": True})


class TestStorageConfiguracao(unittest.IsolatedAsyncioTestCase):
    async def test_chave_do_upstash_isolada_do_site(self):
        self.assertEqual(storage._chave_bot("perfis.json"), "nemesis_bot:perfis.json")

    async def test_importa_dado_antigo_uma_vez_para_namespace_privado(self):
        chamadas = []

        async def redis_mock(*args):
            chamadas.append(args)
            if args == ("GET", "nemesis_bot:perfis.json"):
                return None
            if args == ("GET", "perfis.json"):
                return '{"123": {"xp": 7}}'
            return "OK"

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(storage, "_comando_redis", side_effect=redis_mock):
            resultado = await storage.carregar("perfis.json", {})

        self.assertEqual(resultado, {"123": {"xp": 7}})
        self.assertIn(("SET", "nemesis_bot:perfis.json", '{"123": {"xp": 7}}'), chamadas)

    async def test_upstash_parcial_nao_cai_silenciosamente_no_disco(self):
        with patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", True), patch.object(storage, "USANDO_UPSTASH", False):
            with self.assertRaises(storage.ErroStorage):
                await storage.carregar("estado.json", {})
            with self.assertRaises(storage.ErroStorage):
                await storage.salvar("estado.json", {})


    async def test_salvar_com_expiracao_usa_set_ex_no_upstash(self):
        chamadas = []

        async def redis_mock(*args):
            chamadas.append(args)
            return "OK"

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(
            storage, "_comando_redis", side_effect=redis_mock
        ):
            await storage.salvar_com_expiracao("atividade_mensagem_1_2.json", {"user_id": 3}, 3600)

        self.assertEqual(chamadas[0][0], "SET")
        self.assertEqual(chamadas[0][-2:], ("EX", 3600))

class TestAtualizacaoAtomica(unittest.IsolatedAsyncioTestCase):
    async def test_atualizacao_local_preserva_incrementos_concorrentes(self):
        with tempfile.TemporaryDirectory() as pasta, patch.object(storage, "DATA_DIR", Path(pasta)), patch.multiple(
            storage, USANDO_UPSTASH=False, UPSTASH_CONFIG_INCOMPLETA=False
        ):
            async def incrementar(_):
                return await storage.atualizar_json(
                    "contador.json", {"total": 0},
                    lambda estado: {**estado, "total": estado["total"] + 1},
                )

            await asyncio.gather(*(incrementar(i) for i in range(75)))
            resultado = await storage.carregar("contador.json", {})
            self.assertEqual(resultado["total"], 75)

    async def test_upstash_compare_and_set_repete_apos_conflito(self):
        estado_remoto = {"valor": 1}
        leituras = 0
        chamadas_eval = 0

        async def redis_mock(*args):
            nonlocal leituras, chamadas_eval, estado_remoto
            if args[0] == "GET":
                leituras += 1
                return json.dumps(estado_remoto, separators=(",", ":"))
            if args[0] == "EVAL":
                chamadas_eval += 1
                esperado, novo = args[-2], args[-1]
                atual = json.dumps(estado_remoto, separators=(",", ":"))
                if chamadas_eval == 1:
                    estado_remoto = {"valor": 5}
                    return 0
                if esperado == atual:
                    estado_remoto = json.loads(novo)
                    return 1
                return 0
            raise AssertionError(args)

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(
            storage, "_comando_redis", side_effect=redis_mock
        ):
            resultado = await storage.atualizar_json(
                "contador.json", {"valor": 0},
                lambda atual: {**atual, "valor": atual["valor"] + 1},
            )

        self.assertEqual(leituras, 2)
        self.assertEqual(chamadas_eval, 2)
        self.assertEqual(resultado, {"valor": 6})

    async def test_migracao_legada_usa_cas_na_chave_privada_ausente(self):
        chamadas = []

        async def redis_mock(*args):
            chamadas.append(args)
            if args == ("GET", "nemesis_bot:perfil.json"):
                return None
            if args == ("GET", "perfil.json"):
                return '{"xp": 4}'
            if args[0] == "EVAL":
                self.assertEqual(args[-2], "__NEMESIS_NIL__")
                return 1
            raise AssertionError(args)

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(
            storage, "_comando_redis", side_effect=redis_mock
        ):
            resultado = await storage.atualizar_json(
                "perfil.json", {},
                lambda atual: {**atual, "xp": atual["xp"] + 3},
            )

        self.assertEqual(resultado, {"xp": 7})
        self.assertEqual(chamadas[-1][0], "EVAL")

    async def test_conflito_esgotado_nao_confirma_gravacao(self):
        async def redis_mock(*args):
            if args[0] == "GET":
                return '{"valor": 1}'
            if args[0] == "EVAL":
                return 0
            raise AssertionError(args)

        with patch.multiple(storage, USANDO_UPSTASH=True, UPSTASH_CONFIG_INCOMPLETA=False), patch.object(
            storage, "_comando_redis", side_effect=redis_mock
        ):
            with self.assertRaisesRegex(storage.ErroStorage, "Conflito concorrente"):
                await storage.atualizar_json(
                    "contador.json", {"valor": 0},
                    lambda atual: {**atual, "valor": atual["valor"] + 1},
                    max_tentativas=2,
                )


if __name__ == "__main__":
    unittest.main()


class TestStorageSessaoHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        storage._redis_session = None
        storage._redis_session_loop = None

    async def asyncTearDown(self):
        await storage.fechar_sessao_storage()

    async def test_reutiliza_sessao_http_e_fecha_no_shutdown(self):
        class Resposta:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def json(self):
                return {"result": "PONG"}

        class Sessao:
            def __init__(self, **_):
                self.closed = False
                self.post_count = 0

            def post(self, *_args, **_kwargs):
                self.post_count += 1
                return Resposta()

            async def close(self):
                self.closed = True

        criada = Sessao()
        with patch.multiple(storage, UPSTASH_URL="https://redis.example", UPSTASH_TOKEN="token"), patch.object(
            storage.aiohttp, "ClientSession", return_value=criada
        ) as factory:
            self.assertEqual(await storage._comando_redis("PING"), "PONG")
            self.assertEqual(await storage._comando_redis("PING"), "PONG")
            factory.assert_called_once()
            self.assertEqual(criada.post_count, 2)
            await storage.fechar_sessao_storage()

        self.assertTrue(criada.closed)
        self.assertIsNone(storage._redis_session)
