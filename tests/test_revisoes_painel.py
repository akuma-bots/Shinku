import unittest
from unittest.mock import Mock

from cogs.revisoes import (
    ITENS_POR_PAGINA,
    PainelProvasView,
    _contagens_provas,
    _embed_painel_provas,
    _filtrar_provas,
)


class TestPainelProvas(unittest.TestCase):
    def setUp(self):
        self.registros = [
            {
                "id": f"REV-{indice:03d}",
                "tipo": "missao" if indice % 2 == 0 else "contribuicao",
                "status": ("pendente", "aprovada", "rejeitada")[indice % 3],
                "autor_id": 1000 + indice,
                "auxiliar_id": None,
                "revisor_id": None,
                "referencia_id": f"NM-{indice:03d}",
                "titulo": f"Operação {indice:03d}",
                "timestamp": 1_800_000_000 + indice,
            }
            for indice in range(31)
        ]

    def test_status_and_category_filters_are_combined(self):
        filtradas = _filtrar_provas(self.registros, "pendente", "missao")
        self.assertTrue(all(item["status"] == "pendente" for item in filtradas))
        self.assertTrue(all(item["tipo"] == "missao" for item in filtradas))

    def test_results_are_sorted_newest_first(self):
        filtradas = _filtrar_provas(self.registros, "pendente", "todos")
        self.assertEqual(
            filtradas,
            sorted(filtradas, key=lambda item: item["timestamp"], reverse=True),
        )

    def test_status_counters_cover_all_records(self):
        contagens = _contagens_provas(self.registros)
        self.assertEqual(sum(contagens.values()), len(self.registros))
        self.assertEqual(set(contagens), {"pendente", "aprovada", "rejeitada"})

    def test_dashboard_paginates_eight_records(self):
        view = PainelProvasView(Mock(), 1, 2, "pendente", "todos", 0, 20)
        self.assertEqual(ITENS_POR_PAGINA, 8)
        self.assertTrue(view.anterior.disabled)
        self.assertFalse(view.proxima.disabled)

        ultima = PainelProvasView(Mock(), 1, 2, "pendente", "todos", 2, 20)
        self.assertFalse(ultima.anterior.disabled)
        self.assertTrue(ultima.proxima.disabled)

    def test_dashboard_embed_includes_protocol_and_auxiliary(self):
        itens = _filtrar_provas(self.registros, "pendente", "todos")[:8]
        itens[0]["auxiliar_id"] = 9876
        embed = _embed_painel_provas(
            None,
            "pendente",
            itens,
            "todos",
            0,
            len(itens),
            _contagens_provas(self.registros),
        )
        texto = " ".join(field.value for field in embed.fields)
        self.assertIn(itens[0]["id"], texto)
        self.assertIn("<@9876>", texto)
        self.assertIn("PENDENTES", " ".join(field.name for field in embed.fields))


if __name__ == "__main__":
    unittest.main()
