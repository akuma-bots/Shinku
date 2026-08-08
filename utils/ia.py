import os
import aiohttp

# "groq" (grátis, cadastro simples) · "gemini" (grátis, mas pede verificação
# de idade em algumas contas) · "anthropic" (pago, Claude)
PROVEDOR = os.getenv("IA_PROVEDOR", "groq").lower()

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELO = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

GEMINI_MODELO = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODELO}:generateContent"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELO = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class ErroIA(Exception):
    """Erro ao chamar a API de IA (chave ausente, erro HTTP, timeout etc)."""


async def _chamar_anthropic(system_prompt: str, mensagem: str, max_tokens: int) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ErroIA(
            "ANTHROPIC_API_KEY não configurada no .env. Gere uma em https://platform.claude.com/settings/keys "
            "(pago) — ou troque IA_PROVEDOR=gemini no .env pra usar a opção gratuita."
        )
    headers = {"content-type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    payload = {
        "model": ANTHROPIC_MODELO,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": mensagem}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANTHROPIC_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resposta:
                dados = await resposta.json()
                if resposta.status != 200:
                    erro = dados.get("error", {}).get("message", str(dados))
                    raise ErroIA(f"Erro da API Anthropic ({resposta.status}): {erro}")
    except aiohttp.ClientError as e:
        raise ErroIA(f"Falha de conexão com a API da Anthropic: {e}")

    blocos = [b["text"] for b in dados.get("content", []) if b.get("type") == "text"]
    return "".join(blocos).strip()


async def _chamar_gemini(system_prompt: str, mensagem: str, max_tokens: int) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ErroIA(
            "GEMINI_API_KEY não configurada no .env. Gere uma chave GRÁTIS em https://aistudio.google.com/apikey"
        )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": mensagem}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    url = f"{GEMINI_URL}?key={api_key}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resposta:
                dados = await resposta.json()
                if resposta.status != 200:
                    erro = dados.get("error", {}).get("message", str(dados))
                    raise ErroIA(f"Erro da API Gemini ({resposta.status}): {erro}")
    except aiohttp.ClientError as e:
        raise ErroIA(f"Falha de conexão com a API do Gemini: {e}")

    try:
        partes = dados["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in partes).strip()
    except (KeyError, IndexError):
        raise ErroIA("O Gemini não retornou uma resposta de texto (pode ter bloqueado o conteúdo por segurança).")


async def _chamar_groq(system_prompt: str, mensagem: str, max_tokens: int) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ErroIA(
            "GROQ_API_KEY não configurada no .env. Gere uma chave GRÁTIS (sem verificação de idade, "
            "sem cartão) em https://console.groq.com/keys"
        )
    headers = {"content-type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": GROQ_MODELO,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensagem},
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resposta:
                dados = await resposta.json()
                if resposta.status != 200:
                    erro = dados.get("error", {}).get("message", str(dados))
                    raise ErroIA(f"Erro da API Groq ({resposta.status}): {erro}")
    except aiohttp.ClientError as e:
        raise ErroIA(f"Falha de conexão com a API do Groq: {e}")

    try:
        return dados["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise ErroIA("O Groq não retornou uma resposta de texto.")


async def perguntar_ia(system_prompt: str, mensagem_usuario: str, max_tokens: int = 600) -> str:
    """Manda a pergunta pro provedor de IA configurado (Groq de graça, por padrão,
    Gemini de graça, ou Anthropic/Claude pago — via IA_PROVEDOR no .env) e devolve
    o texto da resposta."""
    if PROVEDOR == "anthropic":
        return await _chamar_anthropic(system_prompt, mensagem_usuario, max_tokens)
    if PROVEDOR == "gemini":
        return await _chamar_gemini(system_prompt, mensagem_usuario, max_tokens)
    return await _chamar_groq(system_prompt, mensagem_usuario, max_tokens)
