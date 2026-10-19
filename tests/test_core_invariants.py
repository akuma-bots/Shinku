from pathlib import Path

import pytest

from cogs.formularios import _paginas_modal, _perguntas_flat, _perguntas_pagina
from cogs.guerras import _resultado
from utils.storage import ErroStorage, _path


@pytest.mark.parametrize(
    ("placar_nemesis", "placar_inimiga", "esperado"),
    [
        (3, 1, "VITÓRIA DA NÊMESIS"),
        (0, 2, "DERROTA DA NÊMESIS"),
        (4, 4, "EMPATE"),
        (0, 0, "EMPATE"),
    ],
)
def test_resultado_guerra(placar_nemesis, placar_inimiga, esperado):
    assert _resultado(placar_nemesis, placar_inimiga) == esperado


def test_formulario_divide_perguntas_em_blocos_validos_para_discord():
    perguntas = [{"texto": f"Pergunta {i}"} for i in range(1, 8)]
    formulario = {
        "paginas": [
            {"titulo": "Candidatura", "perguntas": perguntas},
        ],
    }

    paginas = _paginas_modal(formulario)

    assert len(paginas) == 2
    assert [len(pagina["perguntas"]) for pagina in paginas] == [5, 2]
    assert [p["texto"] for p in _perguntas_flat(formulario)] == [
        p["texto"] for p in perguntas
    ]
    assert _perguntas_pagina(formulario, 0) == perguntas[:5]
    assert _perguntas_pagina(formulario, 1) == perguntas[5:]
    assert _perguntas_pagina(formulario, 2) == []


@pytest.mark.parametrize(
    "nome",
    ["", ".", "..", "../segredo.json", "subpasta/arquivo.json", "subpasta\\\\arquivo.json"],
)
def test_storage_rejeita_caminhos_fora_de_data(nome):
    with pytest.raises(ErroStorage):
        _path(nome)


def test_storage_aceita_nome_de_arquivo_simples():
    caminho = _path("perfil_teste.json")
    assert caminho.name == "perfil_teste.json"
    assert caminho.parent == Path(__file__).resolve().parents[1] / "data"


def test_cogs_criticos_importam_sem_integracao_com_site():
    """Regressão: desafios e missões não podem depender de helpers removidos."""
    import importlib

    assert importlib.import_module("cogs.desafios") is not None
    assert importlib.import_module("cogs.missoes") is not None
