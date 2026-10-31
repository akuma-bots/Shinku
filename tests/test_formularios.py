import unittest
from types import SimpleNamespace

import discord

from cogs import formularios as cog_formularios
from cogs.formularios import _embeds_painel, _embeds_resposta, _paginas_modal, _limpar_sessoes_formularios


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

    def test_sessoes_abandonadas_sao_removidas(self):
        cog_formularios.SESSOES_FORMULARIOS.clear()
        cog_formularios.SESSOES_FORMULARIOS[(1, 2, "antiga")] = {
            "formulario": {},
            "respostas": [],
            "atualizado_em": 50,
        }
        cog_formularios.SESSOES_FORMULARIOS[(1, 2, "recente")] = {
            "formulario": {},
            "respostas": [],
            "atualizado_em": 950,
        }

        _limpar_sessoes_formularios(agora=1000)

        self.assertNotIn((1, 2, "antiga"), cog_formularios.SESSOES_FORMULARIOS)
        self.assertIn((1, 2, "recente"), cog_formularios.SESSOES_FORMULARIOS)
        cog_formularios.SESSOES_FORMULARIOS.clear()

    def test_formulario_staff_tem_20_perguntas_em_quatro_etapas(self):
        formulario = cog_formularios.FORMULARIOS_AUTOMATICOS[0]
        self.assertEqual(len(cog_formularios._perguntas_flat(formulario)), 20)
        self.assertEqual(
            [len(pagina["perguntas"]) for pagina in cog_formularios._paginas_modal(formulario)],
            [5, 5, 5, 5],
        )

    def test_canal_de_recebimento_e_o_canal_oficial_configurado(self):
        self.assertEqual(
            cog_formularios.CANAL_RECEBIMENTO_CANDIDATURAS,
            1563995882540498996,
        )

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
