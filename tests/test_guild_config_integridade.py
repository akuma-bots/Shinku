import unittest
from unittest.mock import AsyncMock, patch

from utils import guild_config


class TestIntegridadeGuildConfig(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_usa_configuracao_padrao(self):
        with patch.object(guild_config, "carregar", new=AsyncMock(return_value=[])):
            config = await guild_config.get_config(123)

        self.assertEqual(config["support_role_id"], guild_config.PADRAO["support_role_id"])
        self.assertEqual(config["contadores"], [])

    async def test_config_nao_dict_nao_quebra_normalizacao(self):
        config = guild_config._normalizar_config(["valor inválido"])

        self.assertEqual(config["contadores"], [])
        self.assertEqual(config["support_role_id"], guild_config.PADRAO["support_role_id"])

    async def test_contadores_corrompidos_sao_filtrados(self):
        config = guild_config._normalizar_config({
            "contadores": [
                None,
                "texto",
                {"tipo": "mensagens", "canal_id": "123", "cargo_id": "456"},
                {"tipo": "inválido", "canal_id": "não-numérico"},
            ]
        })

        self.assertEqual(len(config["contadores"]), 1)
        self.assertEqual(config["contadores"][0]["canal_id"], 123)
        self.assertEqual(config["contadores"][0]["cargo_id"], 456)

    async def test_ids_dos_paineis_sao_normalizados_para_inteiros(self):
        config = guild_config._normalizar_config({
            "ticket_painel_canal_id": "123",
            "ticket_painel_mensagem_id": "456",
            "ranking_mensagem_id": "789",
        })
        self.assertEqual(config["ticket_painel_canal_id"], 123)
        self.assertEqual(config["ticket_painel_mensagem_id"], 456)
        self.assertEqual(config["ranking_mensagem_id"], 789)

    async def test_set_config_recupera_storage_raiz_invalido(self):
        async def atualizar(_arquivo, _padrao, transformador):
            return transformador([])

        with patch.object(guild_config, "atualizar_json", new=AsyncMock(side_effect=atualizar)) as salvar:
            config = await guild_config.set_config(123, desafio_cooldown_minutos=30)

        self.assertEqual(config["desafio_cooldown_minutos"], 30)
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
