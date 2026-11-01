import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import guild_config, storage


class TestGuildConfigAtomico(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.patchers = [
            patch.object(storage, "DATA_DIR", Path(self.tempdir.name)),
            patch.object(storage, "USANDO_UPSTASH", False),
            patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", False),
        ]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)

    async def test_atualizacoes_de_campos_diferentes_nao_se_sobrescrevem(self):
        await asyncio.gather(
            guild_config.set_config(123, canal_eventos_id=111),
            guild_config.set_config(123, canal_parcerias_id=222),
            guild_config.set_config(123, desafio_cooldown_minutos=45),
            guild_config.set_config(123, canal_ranking_id=333),
        )
        config = await guild_config.get_config(123)
        self.assertEqual(config["canal_eventos_id"], 111)
        self.assertEqual(config["canal_parcerias_id"], 222)
        self.assertEqual(config["desafio_cooldown_minutos"], 45)
        self.assertEqual(config["canal_ranking_id"], 333)

    async def test_canais_de_cargo_automatico_sao_atualizados_sem_perda(self):
        await asyncio.gather(*(
            guild_config.definir_canal_cargo_automatico(456, canal, canal + 1000)
            for canal in range(10, 35)
        ))
        config = await guild_config.get_config(456)
        self.assertEqual(len(config["canais_cargo_automatico"]), 25)
        self.assertEqual(config["canais_cargo_automatico"]["17"], 1017)

    async def test_contadores_concorrentes_preservam_registros(self):
        await asyncio.gather(*(
            guild_config.adicionar_contador(789, "membros", canal)
            for canal in range(50, 75)
        ))
        config = await guild_config.get_config(789)
        self.assertEqual(len(config["contadores"]), 25)
        await asyncio.gather(*(
            guild_config.remover_contador(789, canal)
            for canal in range(50, 60)
        ))
        config = await guild_config.get_config(789)
        self.assertEqual(len(config["contadores"]), 15)


if __name__ == "__main__":
    unittest.main()
