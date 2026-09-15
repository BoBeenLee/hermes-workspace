"""Shared plumbing for korea-search: env lookup, HTTP, tag stripping, TTL memo.

Every call here returns a value or ``{"error": ...}`` -- never raises. A tool that
raises is a tool the model cannot talk about; a tool that says "지금 한도 초과다"
lets it answer honestly. Same reason the comfyui plugin funnels through
``error_response`` instead of letting the ComfyUI client's exceptions escape.
"""

from __future__ import annotations

import html
import re
import threading
import time
from typing import Any, Callable, Dict, Optional

import httpx

TIMEOUT_S = 12.0

# Matches web.cache_ttl_minutes (20), which is what web_result_cache already uses
# for web_search. Two different windows for the same question would be a lie.
DEFAULT_TTL_S = 1200.0
_MEMO_MAX = 128

_TAG = re.compile(r"<[^>]+>")


def env(name: str) -> str:
    """Config-aware env lookup (os.environ, then ~/.hermes/.env).

    A bare ``os.getenv`` misses keys that reach the process through the config
    layer, which is how gateway sessions and delegate children get theirs.
    """
    try:
        from agent.web_search_provider import get_provider_env

        return get_provider_env(name)
    except Exception:  # noqa: BLE001 - stripped installs / early import
        import os

        return (os.getenv(name) or "").strip()


def clean(text: str) -> str:
    """Naver and Daum wrap matched terms in ``<b>`` and escape entities."""
    return html.unescape(_TAG.sub("", text or "")).strip()


def err(message: str) -> Dict[str, Any]:
    return {"error": message}


def _explain(response: httpx.Response, who: str) -> str:
    """Turn an HTTP failure into something the model can repeat to a human.

    429 and quota are called out by name because they are the only failures a
    user can act on ("내일 다시") and the only ones a runaway loop produces.
    """
    code = response.status_code
    body = (response.text or "")[:200].replace("\n", " ")
    if code == 429:
        return f"{who} 호출 한도를 넘었다 (429). 오늘 쿼터가 소진됐거나 너무 빨리 불렀다."
    if code in (401, 403):
        return f"{who} 인증이 거부됐다 ({code}). 키 또는 API 사용 설정을 확인해야 한다. {body}"
    return f"{who} 호출 실패 ({code}). {body}"


def _request(method: str, url: str, *, who: str, **kwargs: Any) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            response = client.request(method, url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - network shape varies, message does not
        return err(f"{who} 에 연결하지 못했다: {exc}")
    if response.status_code >= 400:
        return err(_explain(response, who))
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        return err(f"{who} 응답이 JSON 이 아니다: {exc}")


def get_json(url: str, *, who: str, headers: Dict[str, str], params: Dict[str, Any]) -> Dict[str, Any]:
    return _request("GET", url, who=who, headers=headers, params=params)


def post_json(url: str, *, who: str, headers: Dict[str, str], json_body: Dict[str, Any]) -> Dict[str, Any]:
    return _request("POST", url, who=who, headers=headers, json=json_body)


_memo_lock = threading.Lock()
_memo: Dict[Any, Any] = {}


def memoized(key: Any, produce: Callable[[], Dict[str, Any]], ttl: float = DEFAULT_TTL_S) -> Dict[str, Any]:
    """Per-process TTL memo, keyed by the caller's own tuple.

    The quota risk is not a human asking twice -- it is a model looping or a
    cronjob firing, and both repeat the same key within seconds. Failures are
    NOT cached: a 500 would otherwise stick around for the whole window, and a
    429 resolves itself at midnight.
    """
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
    value = produce()
    if isinstance(value, dict) and "error" in value:
        return value
    with _memo_lock:
        if len(_memo) >= _MEMO_MAX:
            # ponytail: clear the whole dict instead of evicting one entry. 128
            # entries and no LRU bookkeeping; the next few calls just re-fetch.
            _memo.clear()
        _memo[key] = (now, value)
    return value


def clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


def require(name: str, who: str) -> Optional[Dict[str, Any]]:
    """``None`` when the key is present, else the error the tool should return."""
    if env(name):
        return None
    return err(f"{who} 를 쓰려면 {name} 가 있어야 하는데 설정돼 있지 않다.")
