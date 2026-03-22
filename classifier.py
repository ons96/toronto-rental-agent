"""LLM-based listing classifier.

Classifies each listing on:
  - private_room (bool)
  - occupants (int, estimated max)
  - cleanliness (1-5)
  - landlord_vibe (1-5)
  - scam_risk (1-5)
  - reasoning (str)

Supports: OpenAI, Anthropic, or local Ollama.
"""
import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """
You are a Toronto rental listing analyst. Analyze the listing below and return ONLY a JSON object.

Listing:
Title: {title}
Price: ${price}/month
Address: {address}
Description:
{description}

Return JSON with exactly these keys:
{{
  "private_room": true/false,        // true = private bedroom (not shared bed/room)
  "occupants": 1-10,                 // estimated MAX people in the unit
  "cleanliness": 1-5,               // 1=filthy/red flags, 5=spotless/well-maintained
  "landlord_vibe": 1-5,             // 1=scummy/aggressive, 5=professional/warm
  "scam_risk": 1-5,                 // 1=obvious scam, 5=very legitimate
  "reasoning": "2-3 sentence summary of your assessment"
}}

Scoring guidance:
- cleanliness: look for words like "clean", "maintained", "renovated" (high) vs "as-is", "fixer", dirty photos described (low)
- landlord_vibe: professional language, clear terms (high) vs aggressive demands, cash-only pressure (low)
- scam_risk: local address, realistic price, specific details (low risk=high score) vs vague, too-good, wire-transfer (high risk=low score)
- occupants: if listing says "shared with 2 others" → 3. If "whole unit" → assume 1-2.
- private_room: false if "shared room", "bunk bed", "co-living pod"

Return ONLY the JSON, no markdown, no explanation.
"""


def classify_listing(listing: Dict[str, Any], config: Dict) -> Dict[str, Any]:
    """Classify a listing using the configured LLM. Returns classification dict."""
    provider = config.get("llm_provider", "openai").lower()
    text = _build_text(listing)
    prompt = CLASSIFY_PROMPT.format(
        title=listing.get("title", ""),
        price=listing.get("price", 0),
        address=listing.get("address", ""),
        description=text[:2000],  # truncate to save tokens
    )

    raw = None
    try:
        if provider == "openai":
            raw = _call_openai(prompt, config)
        elif provider in ("anthropic", "claude"):
            raw = _call_anthropic(prompt, config)
        elif provider == "ollama":
            raw = _call_ollama(prompt, config)
        else:
            logger.warning(f"[classifier] Unknown provider '{provider}', defaulting to openai")
            raw = _call_openai(prompt, config)
    except Exception as e:
        logger.error(f"[classifier] LLM call failed: {e}")
        return _default_classification()

    return _parse_response(raw)


def _build_text(listing: Dict) -> str:
    parts = []
    if listing.get("description"):
        parts.append(listing["description"])
    if listing.get("title"):
        parts.append(listing["title"])
    return " ".join(parts)


def _call_openai(prompt: str, config: Dict) -> str:
    import openai
    client = openai.OpenAI(api_key=config["llm_api_key"])
    resp = client.chat.completions.create(
        model=config.get("llm_model", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _call_anthropic(prompt: str, config: Dict) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=config["llm_api_key"])
    resp = client.messages.create(
        model=config.get("llm_model", "claude-3-haiku-20240307"),
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _call_ollama(prompt: str, config: Dict) -> str:
    import requests
    resp = requests.post(
        config.get("ollama_url", "http://localhost:11434/api/generate"),
        json={
            "model": config.get("llm_model", "llama3"),
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=60,
    )
    return resp.json().get("response", "{}")


def _parse_response(raw: Optional[str]) -> Dict:
    if not raw:
        return _default_classification()
    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)
    try:
        data = json.loads(raw)
        return {
            "private_room": bool(data.get("private_room", True)),
            "occupants": max(1, min(20, int(data.get("occupants", 2)))),
            "cleanliness": max(1, min(5, int(data.get("cleanliness", 3)))),
            "landlord_vibe": max(1, min(5, int(data.get("landlord_vibe", 3)))),
            "scam_risk": max(1, min(5, int(data.get("scam_risk", 3)))),
            "reasoning": str(data.get("reasoning", ""))[:500],
        }
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"[classifier] Failed to parse LLM response: {e} | raw: {raw[:200]}")
        return _default_classification()


def _default_classification() -> Dict:
    return {
        "private_room": True,
        "occupants": 2,
        "cleanliness": 3,
        "landlord_vibe": 3,
        "scam_risk": 3,
        "reasoning": "Classification unavailable.",
    }


def passes_filter(classification: Dict, config: Dict) -> bool:
    """Return True if listing meets user's quality criteria."""
    if not classification.get("private_room", True):
        return False
    if classification.get("occupants", 2) > config.get("max_occupants", 4):
        return False
    if classification.get("cleanliness", 3) < config.get("min_cleanliness", 3):
        return False
    if classification.get("landlord_vibe", 3) < config.get("min_landlord_vibe", 3):
        return False
    if classification.get("scam_risk", 3) < config.get("max_scam_risk", 3):
        return False
    return True
