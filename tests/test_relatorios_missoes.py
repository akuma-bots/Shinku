import csv
import io
import unittest

from cogs.missoes import (
    _filtrar_relatorio_missoes,
    _linhas_csv_relatorio_missoes,
)


class TestRelatoriosMissoes(unittest.TestCase):
    def setUp(self):
        self.agora = 1_800_000_000
        self.revisoes = [
            {
                "id": "A1", "tipo": "missao", "status": "aprovada",
                "autor_id": 101, "auxiliar_id": 202, "recompensa_xp": 100,
                "timestamp": self.agora - 2 * 86400,
                "aprovado_em": self.agora - 86400,
            },
            {
                "id": "B2", "tipo": "especial", "status": "rejeitada",
                "autor_id": 303, "timestamp": self.agora - 20 * 86400,
                "motivo_rejeicao": "Evidência incompleta",
            },
            {
                "id": "C3", "tipo": "contribuicao", "status": "pendente",
                "autor_id": 404, "timestamp": self.agora - 100 * 86400,
            },
            {
                "id": "LEG", "tipo": "missao", "status": "aprovada",
                "autor_id": 505, "timestamp": "inválida",
            },
            {
                "id": "PVP", "tipo": "pvp", "status": "aprovada",
                "autor_id": 606, "recompensa_xp": 500, "timestamp": self.agora,
            },
        ]

    def test_periodo_filtra_por_data_de_envio(self):
        dados = _filtrar_relatorio_missoes(self.revisoes, "7", self.agora)
        self.assertEqual([item["id"] for item in dados], ["A1"])

    def test_historico_total_preserva_legados_sem_data_e_ignora_pvp(self):
        dados = _filtrar_relatorio_missoes(self.revisoes, "total", self.agora)
        self.assertEqual({item["id"] for item in dados}, {"A1", "B2", "C3", "LEG"})

    def test_periodo_nao_inclui_registro_com_data_invalida(self):
        dados = _filtrar_relatorio_missoes(self.revisoes, "90", self.agora)
        self.assertNotIn("LEG", {item["id"] for item in dados})

    def test_csv_exporta_colunas_de_auditoria_e_divide_xp_60_40(self):
        conteudo = _linhas_csv_relatorio_missoes([self.revisoes[0]])
        leitor = csv.DictReader(io.StringIO(conteudo), delimiter=";")
        linha = next(leitor)
        self.assertEqual(linha["protocolo"], "A1")
        self.assertEqual(linha["xp_responsavel"], "60")
        self.assertEqual(linha["xp_auxiliar"], "40")
        self.assertEqual(float(linha["aprovado_em"]), float(self.agora - 86400))

    def test_csv_nao_estima_recompensa_legada_ou_nao_aprovada(self):
        conteudo = _linhas_csv_relatorio_missoes([self.revisoes[1], self.revisoes[2], self.revisoes[3]])
        linhas = list(csv.DictReader(io.StringIO(conteudo), delimiter=";"))
        self.assertEqual([linha["recompensa_xp_registrada"] for linha in linhas], ["", "", ""])
        self.assertEqual([linha["xp_responsavel"] for linha in linhas], ["", "", ""])


if __name__ == "__main__":
    unittest.main()
