"""Kakao: place search (카카오맵 REST) and Daum web search.

Both ride one ``KAKAO_REST_API_KEY``, but they are billed against *different*
daily pools -- 카카오맵 100,000 and Daum 검색 50,000 -- so a chatty web search
never eats the place budget.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.web_search_provider import WebSearchProvider

from ._util import clamp, clean, env, err, get_json, memoized, require

logger = logging.getLogger(__name__)

KEY = "KAKAO_REST_API_KEY"
PLACE_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
DAUM_WEB_URL = "https://dapi.kakao.com/v2/search/web"

# Kakao returns at most 45 documents for any query no matter how large
# total_count is (meta.pageable_count caps at 45), so paging past it is wasted.
PLACE_HARD_CAP = 45
RADIUS_MAX_M = 20000

CATEGORY_CODES = {
    "MT1": "대형마트", "CS2": "편의점", "PS3": "어린이집,유치원", "SC4": "학교",
    "AC5": "학원", "PK6": "주차장", "OL7": "주유소,충전소", "SW8": "지하철역",
    "BK9": "은행", "CT1": "문화시설", "AG2": "중개업소", "PO3": "공공기관",
    "AT4": "관광명소", "AD5": "숙박", "FD6": "음식점", "CE7": "카페",
    "HP8": "병원", "PM9": "약국",
}


def _headers() -> Dict[str, str]:
    return {"Authorization": f"KakaoAK {env(KEY)}"}


def _place_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "name": doc.get("place_name", ""),
        "category": doc.get("category_name", ""),
        # Road address is what people type into a nav app; the lot address is the
        # fallback for places that predate the road-name system.
        "address": doc.get("road_address_name") or doc.get("address_name", ""),
        "map_url": doc.get("place_url", ""),
    }
    if doc.get("phone"):
        row["phone"] = doc["phone"]
    for src, dst in (("x", "lon"), ("y", "lat")):
        try:
            row[dst] = float(doc[src])
        except (KeyError, TypeError, ValueError):
            pass
    # Only present when the caller passed x/y, so its absence is not an error.
    if doc.get("distance"):
        row["distance_m"] = doc["distance"]
    return row


def place_search(
    query: str,
    category: Optional[str] = None,
    lon: Optional[float] = None,
    lat: Optional[float] = None,
    radius_m: Optional[int] = None,
    size: int = 5,
) -> Dict[str, Any]:
    missing = require(KEY, "카카오 장소 검색")
    if missing:
        return missing
    if not (query or "").strip():
        return err("query 가 비었다.")

    size = clamp(size, 1, 15, 5)
    params: Dict[str, Any] = {"query": query.strip(), "size": size}
    if category:
        code = category.strip().upper()
        if code not in CATEGORY_CODES:
            return err(f"category '{category}' 는 없는 코드다. 가능한 값: {', '.join(sorted(CATEGORY_CODES))}")
        params["category_group_code"] = code
    if lon is not None and lat is not None:
        params["x"], params["y"] = lon, lat
        # distance sort only means anything with a centre, and Kakao rejects it
        # without one -- so it is bound to the same branch that sets x/y.
        params["sort"] = "distance"
        if radius_m is not None:
            params["radius"] = clamp(radius_m, 0, RADIUS_MAX_M, RADIUS_MAX_M)

    def fetch() -> Dict[str, Any]:
        data = get_json(PLACE_URL, who="카카오 장소 검색", headers=_headers(), params=params)
        if "error" in data:
            return data
        docs = data.get("documents") or []
        meta = data.get("meta") or {}
        out: Dict[str, Any] = {
            "places": [_place_row(d) for d in docs],
            "total_found": meta.get("total_count"),
            "reachable_max": min(meta.get("pageable_count") or 0, PLACE_HARD_CAP),
        }
        # Kakao's own disambiguation of the query's region token. Worth passing
        # through: "성수동" alone is 1가 and 2가, and the model has no other way
        # to know it silently picked one.
        same = meta.get("same_name") or {}
        if same.get("region"):
            out["region_note"] = {
                "keyword": same.get("keyword"),
                "picked": same.get("selected_region"),
                "others": same.get("region"),
            }
        return out

    return memoized(("kakao_place", tuple(sorted(params.items()))), fetch)


def daum_web(query: str, limit: int = 5) -> Optional[List[Dict[str, Any]]]:
    """Daum web-document rows in the web_search wire shape, or None on failure.

    None rather than an error dict: the caller is a search provider that has a
    second path to try, and it needs to distinguish "Daum said no" from "Daum
    returned nothing", which is a legitimate empty result.
    """
    params = {"query": query, "size": clamp(limit, 1, 50, 5), "sort": "accuracy"}
    data = get_json(DAUM_WEB_URL, who="Daum 웹문서 검색", headers=_headers(), params=params)
    if "error" in data:
        logger.info("daum web search failed: %s", data["error"])
        return None
    return [
        {
            "url": doc.get("url", ""),
            "title": clean(doc.get("title", "")),
            "description": clean(doc.get("contents", "")),
            "position": i,
        }
        for i, doc in enumerate(data.get("documents") or [], start=1)
    ]


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text or "")


def _delegate(query: str, limit: int) -> Optional[Dict[str, Any]]:
    """Hand a non-Korean query back to the bundled keyless ring.

    Private import on purpose: there is no public seam for "run the default
    search", and re-implementing the ring would be worse. This install is 410
    commits behind upstream, so treat the import as breakable.
    """
    try:
        from plugins.web.keyless_mcp import search_with_failover
    except Exception as exc:  # noqa: BLE001
        logger.info("keyless ring unavailable, staying on Daum: %s", exc)
        return None
    return search_with_failover("daum", query, limit)


class DaumWebSearchProvider(WebSearchProvider):
    """``web_search`` backed by Daum for Hangul queries, the keyless ring otherwise.

    A provider rather than a fourth tool. The model never has to learn anything:
    every ``web_search`` call already in the prompts and in the daemon gets the
    Korean index for free. A tool would have to win an argument with the model
    on every turn, and this host answers on a free-tier model.
    """

    @property
    def name(self) -> str:
        return "daum"

    @property
    def display_name(self) -> str:
        return "Daum (Kakao)"

    def is_available(self) -> bool:
        # Local check only -- the picker calls this on every paint.
        return bool(env(KEY))

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "free",
            "tag": "한글 질의는 Daum 웹문서 검색, 그 외는 기존 keyless 링",
            "env_vars": [{
                "key": KEY,
                "prompt": "Kakao REST API key",
                "url": "https://developers.kakao.com",
            }],
        }

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"success": False, "error": "query 가 비었다."}

        if not _has_hangul(query):
            delegated = _delegate(query, limit)
            if delegated is not None:
                return delegated
            # Ring gone. Daum indexes English too, just less well -- a degraded
            # answer beats web_search going dark for every non-Korean query.

        rows = daum_web(query, limit)
        if rows is None:
            return {"success": False, "error": f"Daum 웹문서 검색이 실패했다 ({KEY} 확인)."}
        return {"success": True, "data": {"web": rows}}
