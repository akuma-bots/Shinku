import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import catalogo_missoes, storage


class TestCatalogoMissoesStorageAtomico(unittest.IsolatedAsyncioTestCase):
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

    async def test_sincronizacao_preserva_missoes_personalizadas(self):
        await catalogo_missoes.sincronizar_catalogo(
            777,
            [{"id": "PAD-1", "tipo": "missao", "titulo": "Padrão", "recompensa_xp": 10}],
        )
        from utils import missoes
        personalizada = await missoes.criar(
            777, "especial", "Personalizada", "Não deve ser removida", 50
        )
        await catalogo_missoes.sincronizar_catalogo(
            777,
            [{"id": "PAD-1", "tipo": "missao", "titulo": "Padrão atualizado", "recompensa_xp": 20}],
        )
        todas = await missoes.listar(777, apenas_ativas=False)
        self.assertIn(personalizada["id"], {item["id"] for item in todas})
        padrao = next(item for item in todas if item["id"] == "PAD-1")
        self.assertEqual(padrao["titulo"], "Padrão atualizado")

    async def test_salvamento_concorrente_preserva_ids_de_mensagens(self):
        await asyncio.gather(*(
            catalogo_missoes.salvar_mensagem_discord(
                888, f"MISS-{n}", 9000 + n, [10000 + n, 20000 + n]
            )
            for n in range(25)
        ))
        registros = await storage.carregar(catalogo_missoes.ARQUIVO_MENSAGENS_DISCORD, {})
        guild = registros["888"]
        self.assertEqual(len(guild), 25)
        self.assertEqual(guild["MISS-7"]["discord_message_ids"], [10007, 20007])


if __name__ == "__main__":
    unittest.main()
