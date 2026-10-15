#!/usr/bin/env python3
"""Refresh the game-code catalog from the configured public code-list pages.

The updater is deliberately conservative: if a source cannot be parsed with
confidence, it fails rather than replacing the catalog with an empty/incorrect
list. Existing reward notes and redemption requirements are preserved.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "codigos_jogos.json"
HEADERS = {"User-Agent": "NemesisCodesUpdater/1.0 (weekly public code catalog)"}
SOURCES = {
    "shigaku": "https://urgametips.com/shigaku-codes/",
    "gakuran": "https://rocodes.gg/codes/gakuran",
    "fistborn": "https://rocodes.gg/codes/fistborn",
}
# Only match code-like tokens from a page's code sections, never arbitrary page text.
CODE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_!.-]{2,39})(?![A-Za-z0-9_])")
EXCLUDED = {
    "active", "expired", "working", "codes", "code", "rewards", "reward",
    "requirements", "requirement", "roblox", "shigaku", "gakuran", "fistborn",
    "updated", "latest", "new", "free", "copy", "redeem", "click", "here",
}


def fetch(url: str) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"Fonte retornou HTTP {response.status}: {url}")
        return response.read().decode("utf-8", errors="replace")


def html_to_text(html: str) -> str:
    # Preserve heading/row boundaries to make section extraction more reliable.
    html = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)</?(?:h[1-6]|tr|li|p|br|div|section|article|table|ul|ol)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"[ \t\r]+", " ", unescape(html))


def active_section(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        low = line.lower()
        if start is None and re.search(r"\b(active|working|valid|currently working)\b.{0,35}\bcodes?\b|\bcodes?\b.{0,35}\b(active|working|valid)\b", low):
            start = index
            continue
        if start is not None and re.search(r"\b(expired|inactive|invalid)\b.{0,25}\bcodes?\b|\bcodes?\b.{0,25}\b(expired|inactive|invalid)\b", low):
            end = index
            break
    if start is None:
        raise RuntimeError("Não foi possível identificar com segurança a seção de códigos ativos.")
    section = "\n".join(lines[start + 1:end])
    if len(section) < 20:
        raise RuntimeError("A seção de códigos ativos está vazia ou incompleta.")
    return section


def extract_codes(section: str, existing: dict) -> list[dict]:
    found: list[str] = []
    known = {item["codigo"].casefold(): item for item in existing.get("codigos", [])}
    for raw in CODE_TOKEN.findall(section):
        token = raw.strip("._!-")
        if token.lower() in EXCLUDED or len(token) < 4:
            continue
        # Avoid likely prose tokens; preserve only tokens already known or code-like
        # values containing digits, mixed case, or all-caps names.
        if token.casefold() not in known and not (
            any(char.isdigit() for char in token)
            or (token.isupper() and len(token) >= 5)
            or (any(char.islower() for char in token) and any(char.isupper() for char in token))
        ):
            continue
        if token.casefold() not in {item.casefold() for item in found}:
            found.append(token)
    if not found:
        raise RuntimeError("Nenhum código foi identificado; catálogo existente preservado.")
    result = []
    for token in found:
        previous = known.get(token.casefold())
        result.append({
            "codigo": token,
            "recompensa": previous.get("recompensa", "Recompensa não confirmada; consulte a fonte") if previous else "Recompensa não confirmada; consulte a fonte",
        })
    return result


def calcular_semana(data: date) -> tuple[date, date]:
    """Retorna a segunda-feira e o domingo da semana que contém a data."""
    inicio = data - timedelta(days=data.weekday())
    return inicio, inicio + timedelta(days=6)


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    # Use o fuso do servidor da NÊMESIS, não o UTC do runner do GitHub.
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    week_start, week_end = calcular_semana(today)
    changed = False
    failures = []

    for key, url in SOURCES.items():
        try:
            text = html_to_text(fetch(url))
            section = active_section(text)
            refreshed = extract_codes(section, catalog["jogos"][key])
            catalog["jogos"][key]["codigos"] = refreshed
            catalog["jogos"][key]["fonte"] = url
            print(f"{key}: {len(refreshed)} códigos ativos identificados.")
        except Exception as exc:  # source markup changes should fail closed
            failures.append(f"{key}: {exc}")
            print(f"ERRO {key}: {exc}", file=sys.stderr)

    if failures:
        print("Atualização semanal incompleta; o catálogo não será gravado.", file=sys.stderr)
        return 1

    catalog["atualizado_em"] = today.isoformat()
    catalog["semana_referente"] = {
        "inicio": week_start.isoformat(),
        "fim": week_end.isoformat(),
        "fuso": "America/Sao_Paulo",
    }
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catálogo atualizado para a semana {week_start.isoformat()} a {week_end.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
