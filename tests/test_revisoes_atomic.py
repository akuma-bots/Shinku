import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import revisoes, storage


class TestRevisoesAtualizacaoAtomica(unittest.IsolatedAsyncioTestCase):
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

    async def test_criacoes_concorrentes_nao_sobrescrevem_protocolos(self):
        await asyncio.gather(*(
            revisoes.criar_pendencia(
                100, "missao", uid, f"ref-{uid}",
                f"https://cdn.example/{uid}.png", f"Prova {uid}",
                recompensa_xp=50,
            )
            for uid in range(1, 41)
        ))
        registros = await revisoes.listar(100)
        self.assertEqual(len(registros), 40)
        self.assertEqual(len({item["id"] for item in registros}), 40)

    async def test_criacao_pvp_concorrente_permanece_idempotente(self):
        resultados = await asyncio.gather(*(
            revisoes.criar_pendencia(
                200, "pvp", 10, "desafio-xyz",
                "https://cdn.example/pvp.png", "Desafio PvP",
                recompensa_xp=100,
            )
            for _ in range(12)
        ))
        registros = await revisoes.listar(200)
        self.assertEqual(len(registros), 1)
        self.assertEqual(len({item["id"] for item in resultados}), 1)

    async def test_apenas_uma_decisao_concorrente_pode_aprovar(self):
        registro = await revisoes.criar_pendencia(
            300, "missao", 10, "ref-aprovar",
            "https://cdn.example/aprovar.png", "Prova para aprovar",
            recompensa_xp=100,
        )
        decisoes = await asyncio.gather(
            revisoes.aprovar(300, registro["id"], 501),
            revisoes.aprovar(300, registro["id"], 502),
        )
        confirmadas = [item for item in decisoes if item is not None]
        self.assertEqual(len(confirmadas), 1)
        final = await revisoes.get(300, registro["id"])
        self.assertEqual(final["status"], "aprovada")
        eventos = [
            item for item in final["trilha_auditoria"]
            if item.get("evento") == "protocolo_aprovado"
        ]
        self.assertEqual(len(eventos), 1)


if __name__ == "__main__":
    unittest.main()
