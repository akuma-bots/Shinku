import os
import aiohttp

TAVILY_URL = "https://api.tavily.com/search"


class ErroPesquisa(Exception):
    """Erro ao pesquisar na web (chave ausente, erro HTTP, timeout etc)."""


async def pesquisar_web(query: str, max_resultados: int = 4) -> str:
    """Pesquisa na web via Tavily e devolve um resumo em texto (resposta direta +
    trechos das páginas mais relevantes) pra usar como contexto de uma IA."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ErroPesquisa(
            "TAVILY_API_KEY não configurada no .env. Gere uma chave GRÁTIS (sem cartão) em https://tavily.com"
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_resultados,
        "include_answer": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TAVILY_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)
            ) as resposta:
                dados = await resposta.json()
                if resposta.status != 200:
                    erro = dados.get("error", str(dados))
                    raise ErroPesquisa(f"Erro da API Tavily ({resposta.status}): {erro}")
    except aiohttp.ClientError as e:
        raise ErroPesquisa(f"Falha de conexão com a API do Tavily: {e}")

    partes = []
    if dados.get("answer"):
        partes.append(f"Resumo direto: {dados['answer']}")
    for r in dados.get("results", [])[:max_resultados]:
        titulo = r.get("title", "")
        conteudo = (r.get("content", "") or "")[:500]
        url = r.get("url", "")
        partes.append(f"- {titulo}: {conteudo} (fonte: {url})")

    return "\n".join(partes) if partes else "(nenhum resultado encontrado)"
