import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.missoes import Missoes


class TestMissionPanelEmbedDesign(unittest.IsolatedAsyncioTestCase):
    async def test_painel_tem_resumo_visual_e_missoes_compactas(self):
        dados = {
            "missoes": [
                {
                    "id": "SHI-001",
                    "jogo": "shigaku",
                    "tipo": "missao",
                    "titulo": "Operação de Reconhecimento",
                    "descricao": "Investigue a área designada e envie evidências para validação.",
                    "recompensa_xp": 60,
                    "ativa": True,
                },
                {
                    "id": "SHI-002",
                    "jogo": "shigaku",
                    "tipo": "especial",
                    "titulo": "Operação Encerrada",
                    "descricao": "Registro arquivado.",
                    "recompensa_xp": 25,
                    "ativa": False,
                },
                {
                    "id": "GAK-001",
                    "jogo": "gakuran",
                    "tipo": "missao",
                    "titulo": "Outro jogo",
                    "descricao": "Não deve aparecer neste painel.",
                    "recompensa_xp": 10,
                    "ativa": True,
                },
            ]
        }
        cog = Missoes.__new__(Missoes)
        guild = SimpleNamespace(id=1563995879981981817)

        with patch("cogs.missoes.missoes._guild", new=AsyncMock(return_value=dados)):
            embed = await cog._montar_painel_missoes(guild, "shigaku")

        self.assertIn("CENTRAL DE MISSÕES", embed.title)
        self.assertIn("Shigaku", embed.description)
        self.assertIn("/missao-enviar-prova", embed.description)
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["🟢 EM OPERAÇÃO"], "**1**")
        self.assertEqual(fields["⛔ ENCERRADAS"], "**1**")
        self.assertEqual(fields["◈ NO CATÁLOGO"], "**2**")
        self.assertTrue(any("Operação de Reconhecimento" in name for name in fields))
        self.assertTrue(any("Operação Encerrada" in name for name in fields))
        self.assertFalse(any("Outro jogo" in name for name in fields))
        self.assertIn("PÁGINA:shigaku", embed.footer.text)

    async def test_painel_vazio_e_recompensa_invalida_nao_quebram(self):
        dados = {
            "missoes": [
                {
                    "id": "SHI-X",
                    "jogo": "shigaku",
                    "tipo": "missao",
                    "titulo": "Teste",
                    "descricao": "Teste",
                    "recompensa_xp": "inválida",
                    "ativa": True,
                }
            ]
        }
        cog = Missoes.__new__(Missoes)
        guild = SimpleNamespace(id=1563995879981981817)
        with patch("cogs.missoes.missoes._guild", new=AsyncMock(return_value=dados)):
            embed = await cog._montar_painel_missoes(guild, "shigaku")
        self.assertTrue(any("0 XP" in field.name for field in embed.fields))

        with patch(
            "cogs.missoes.missoes._guild",
            new=AsyncMock(return_value={"missoes": []}),
        ):
            vazio = await cog._montar_painel_missoes(guild, "shigaku")
        self.assertIn("CATÁLOGO VAZIO", " ".join(field.name for field in vazio.fields))

    async def test_painel_respeita_limite_de_caracteres_do_embed(self):
        atividades = [
            {
                "id": f"SHI-{i:03d}",
                "jogo": "shigaku",
                "tipo": "missao",
                "titulo": "Operação " + ("Reconhecimento " * 10),
                "descricao": "Descrição " * 40,
                "recompensa_xp": 60,
                "ativa": True,
            }
            for i in range(1, 26)
        ]
        cog = Missoes.__new__(Missoes)
        guild = SimpleNamespace(id=1563995879981981817)
        with patch(
            "cogs.missoes.missoes._guild",
            new=AsyncMock(return_value={"missoes": atividades}),
        ):
            embed = await cog._montar_painel_missoes(guild, "shigaku")

        tamanho = (
            len(embed.title or "")
            + len(embed.description or "")
            + sum(len(field.name) + len(field.value) for field in embed.fields)
            + len(embed.footer.text or "")
            + len(embed.author.name or "")
        )
        self.assertLessEqual(tamanho, 6000)
        self.assertTrue(any("CATÁLOGO COMPLEMENTAR" in field.name for field in embed.fields))
        self.assertLessEqual(len(embed.fields), 25)


if __name__ == "__main__":
    unittest.main()
