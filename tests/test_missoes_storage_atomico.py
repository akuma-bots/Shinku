import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import missoes, storage


class TestMissoesStorageAtomico(unittest.IsolatedAsyncioTestCase):
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

    async def test_criacoes_concorrentes_nao_perdem_missoes(self):
        await asyncio.gather(*(
            missoes.criar(123, "missao", f"Missão {n}", "Descrição", 10)
            for n in range(50)
        ))
        resultado = await missoes.listar(123, apenas_ativas=False)
        self.assertEqual(len(resultado), 50)
        self.assertEqual(len({item["id"] for item in resultado}), 50)

    async def test_edicao_estado_e_recompensa_sao_atualizados_atomicamente(self):
        missao = await missoes.criar(
            654, "missao", "Original", "Descrição", 10
        )
        editada = await missoes.atualizar_missao(
            654, missao["id"], {"titulo": "Atualizada", "recompensa_xp": 75}
        )
        self.assertEqual(editada["titulo"], "Atualizada")
        self.assertEqual(editada["pontos"], 75)

        alternada = await missoes.alternar_estado_missao(654, missao["id"], 999)
        self.assertFalse(alternada["ativa"])
        self.assertEqual(alternada["atualizado_por"], 999)

        await asyncio.gather(*(
            missoes.registrar_recompensa_aplicada(654, missao["id"], "REV-1")
            for _ in range(8)
        ))
        final = await missoes.get(654, missao["id"])
        self.assertEqual(final["recompensas_aplicadas"], ["REV-1"])

    async def test_desativacao_preserva_missoes_criadas_em_paralelo(self):
        criadas = await asyncio.gather(*(
            missoes.criar(456, "especial", f"Especial {n}", "Descrição", 20)
            for n in range(8)
        ))
        await asyncio.gather(*(
            missoes.desativar(456, item["id"])
            for item in criadas[:4]
        ))
        ativas = await missoes.listar(456)
        todas = await missoes.listar(456, apenas_ativas=False)
        self.assertEqual(len(ativas), 4)
        self.assertEqual(len(todas), 8)


if __name__ == "__main__":
    unittest.main()
