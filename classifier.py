"""LLM-based listing classifier.

Classifies each listing on:
  - private_room (bool)
  - occupants (int, estimated max)
  - cleanliness (1-5)
  - landlord_vibe (1-5)
  - scam_risk (1-5)
  - reasoning (str)

Supports: noobrouter, supacoder, openai-compatible, anthropic, ollama.
Default: noobrouter (free) with supacoder fallback.
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
{{"private_room": true/false, "occupants": 1-10, "cleanliness": 1-5, "landlord_vibe": 1-5, "scam_risk": 1-5, "reasoning": "2-3 sentence summary"}}

Scoring:
- cleanliness: 5=clean/renovated, 1=dirty/as-is
- landlord_vibe: 5=professional/warm, 1=aggressive/cash-only pressure
- scam_risk: 5=very legitimate, 1=obvious scam/wire transfer demand
- occupants: count everyone in unit (not just bedrooms)
- private_room: false ONLY if shared bed/bunk/co-living pod

Return ONLY the JSON, no markdown.
"""

# Provider configs loaded from config at runtime (keys stay in config.json)
_NOOBROUTER_URL = "https://noobrouter.azurewebsites.net/v1"
_SUPACODER_URL = "https://supacoder.top/v1"
_NOOBROUTER_DEFAULT_KEY = "sk-zenith-giveaway"  # public giveaway key
_SUPACODER_DEFAULT_KEY = "sk-NRLw4ynN7vawdmlOROiKC2H3L18PjYhQwCDA5JQA0y4f6f18"  # public key


def classify_listing(listing: Dict[str, Any], config: Dict) -> Dict[str, Any]:
    """Classify a listing. Falls back through providers automatically."""
    prompt = CLASSIFY_PROMPT.format(
        title=listing.get("title", ""),
        price=listing.get("price", 0),
        address=listing.get("address", ""),
        description=_build_text(listing)[:2000],
    )

    # Build provider list: custom config first, then built-in free providers
    providers = _get_provider_list(config)

    for base_url, api_key, model in providers:
        try:
            raw = _call_openai_compat(prompt, base_url, api_key, model)
            if raw:
                result = _parse_response(raw)
                if result["reasoning"] != "Classification unavailable.":
                    return result
        except Exception as e:
            logger.debug(f"[classifier] Provider {base_url} failed: {e}")
            continue

    logger.warning("[classifier] All providers failed, using default classification")
    return _default_classification()


def _get_provider_list(config: Dict):
    """Return ordered list of (base_url, api_key, model) tuples."""
    providers = []

    provider = config.get("llm_provider", "noobrouter").lower()

    if provider == "noobrouter":
        model = config.get("llm_model", "openai/gpt-5.1")
        key = config.get("noobrouter_api_key", _NOOBROUTER_DEFAULT_KEY)
        providers.append((_NOOBROUTER_URL, key, model))
    elif provider == "supacoder":
        model = config.get("llm_model", "gpt-5.4")
        key = config.get("supacoder_api_key", config.get("llm_api_key", _SUPACODER_DEFAULT_KEY))
        providers.append(("https://supacoder.top/v1", key, model))
    elif provider in ("openai", "openai-compatible", "gateway"):
        base_url = config.get("llm_base_url", "https://api.openai.com/v1")
        key = config.get("llm_api_key", "")
        model = config.get("llm_model", "gpt-4o-mini")
        providers.append((base_url, key, model))
    elif provider == "anthropic":
        # Handled separately below
        pass
    elif provider == "ollama":
        base_url = config.get("ollama_url", "http://localhost:11434/v1")
        model = config.get("llm_model", "llama3")
        providers.append((base_url, "ollama", model))

    # Always append built-in free fallbacks (with config-overridable keys)
    noob_key = config.get("noobrouter_api_key", _NOOBROUTER_DEFAULT_KEY)
    supa_key = config.get("supacoder_api_key", _SUPACODER_DEFAULT_KEY)
    providers.extend([
        (_NOOBROUTER_URL, noob_key, "openai/gpt-5.1"),
        (_SUPACODER_URL, supa_key, "gpt-5.4"),
    ])
    return providers


def _call_openai_compat(prompt: str, base_url: str, api_key: str, model: str) -> Optional[str]:
    """Call any OpenAI-compatible endpoint."""
    import requests
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 350,
            "temperature": 0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _build_text(listing: Dict) -> str:
    return " ".join(filter(None, [listing.get("description", ""), listing.get("title", "")]))


def _parse_response(raw: Optional[str]) -> Dict:
    if not raw:
        return _default_classification()
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)
    # Extract first JSON object if there's surrounding text
    m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if m:
        raw = m.group(0)
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
        logger.warning(f"[classifier] Parse failed: {e} | raw: {raw[:200]}")
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
