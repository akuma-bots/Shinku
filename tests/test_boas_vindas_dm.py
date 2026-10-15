import json
from pathlib import Path

from cogs.boas_vindas_dm import carregar_catalogo_codigos, TAG_GANGUE, CONVITE_NEMESIS


def test_welcome_codes_catalog_has_all_games_and_requirements():
    catalogo = carregar_catalogo_codigos()
    assert {"shigaku", "gakuran", "fistborn"}.issubset(catalogo["jogos"])
    for jogo in ("shigaku", "gakuran", "fistborn"):
        dados = catalogo["jogos"][jogo]
        assert dados["codigos"]
        assert dados["requisitos"]
        assert dados["fonte"].startswith("https://")


def test_welcome_uses_nemesis_tag_and_invite():
    assert TAG_GANGUE == "NΞM"
    assert CONVITE_NEMESIS.startswith("https://discord.gg/")


def test_codes_catalog_is_valid_json():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "codigos_jogos.json").read_text(encoding="utf-8"))
    assert len(data["atualizado_em"]) == 10
    assert data["atualizado_em"][4] == "-" and data["atualizado_em"][7] == "-"
    if "semana_referente" in data:
        semana = data["semana_referente"]
        assert semana["inicio"] <= semana["fim"]
        assert semana["fuso"]
