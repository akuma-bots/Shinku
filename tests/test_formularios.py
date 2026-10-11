import unittest
from types import SimpleNamespace

import discord

from cogs.formularios import _embeds_painel, _embeds_resposta, _paginas_modal


class TestFormularios(unittest.TestCase):
    def test_descricao_longa_e_dividida_sem_ultrapassar_limite_do_discord(self):
        descricao = ("Texto da descrição da NÊMESIS.\n" * 500)
        embeds = _embeds_painel({
            "id": "teste",
            "titulo_painel": "Formulário de teste",
            "descricao_painel": descricao,
        })

        self.assertGreater(len(embeds), 1)
        self.assertTrue(all(embed.description for embed in embeds))
        self.assertTrue(all(len(embed.description) <= 4096 for embed in embeds))

    def test_etapas_com_mais_de_cinco_perguntas_sao_divididas_para_modais(self):
        formulario = {
            "paginas": [{
                "titulo": "Etapa única",
                "perguntas": [
                    {"id": str(i), "texto": f"Pergunta {i}"}
                    for i in range(12)
                ],
            }]
        }

        paginas = _paginas_modal(formulario)
        self.assertEqual([len(p["perguntas"]) for p in paginas], [5, 5, 2])

    def test_candidatura_longa_respeita_limite_de_campos_por_embed(self):
        perguntas = [
            {"id": str(i), "texto": f"Pergunta {i}", "tipo": "longa"}
            for i in range(61)
        ]
        formulario = {
            "nome": "Teste",
            "paginas": [{"titulo": "Etapa", "perguntas": perguntas}],
        }
        resposta = {
            "id": "resposta-teste",
            "autor_id": 123456789,
            "respostas": [f"Resposta {i}" for i in range(61)],
        }
        guild = SimpleNamespace(name="NÊMESIS")

        embeds = _embeds_resposta(formulario, resposta, guild)

        self.assertEqual(len(embeds), 3)
        self.assertTrue(all(len(embed.fields) <= 25 for embed in embeds))
        self.assertEqual(
            sum(len(embed.fields) - 1 for embed in embeds),
            61,
        )


if __name__ == "__main__":
    unittest.main()
