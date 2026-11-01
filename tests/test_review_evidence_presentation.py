import unittest

from cogs.revisoes import _embed_revisao


class TestReviewEvidencePresentation(unittest.TestCase):
    def test_embed_exibe_participante_auxiliar_e_recompensa_xp(self):
        revisao = {
            "id": "REV-1234",
            "tipo": "missao",
            "autor_id": 123456789012345678,
            "auxiliar_id": 223456789012345678,
            "referencia_id": "NEM-001",
            "titulo": "Operação de Reconhecimento",
            "descricao": "Evidência enviada para validação.",
            "print_url": "https://cdn.discordapp.com/attachments/1/2/prova.png",
            "recompensa_xp": 60,
            "status": "pendente",
            "timestamp": 1793500000,
        }

        embed = _embed_revisao(revisao)

        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertIn("◈ PARTICIPANTE", campos)
        self.assertIn("◈ COLABORADOR", campos)
        self.assertEqual(campos["◈ RECOMPENSA PREVISTA"], "**+60 XP**")
        self.assertIn("◈ DIRETRIZES DE ANÁLISE", campos)
        self.assertEqual(embed.image.url, revisao["print_url"])

    def test_embed_legado_sem_recompensa_continua_compativel(self):
        revisao = {
            "id": "REV-LEGADO",
            "tipo": "pvp",
            "autor_id": 123456789012345678,
            "referencia_id": "LUTA-001",
            "titulo": "Desafio competitivo",
            "descricao": "Registro legado.",
            "print_url": "https://cdn.discordapp.com/attachments/1/2/prova.png",
            "status": "pendente",
        }

        embed = _embed_revisao(revisao)

        self.assertFalse(any(campo.name == "◈ RECOMPENSA PREVISTA" for campo in embed.fields))


if __name__ == "__main__":
    unittest.main()
