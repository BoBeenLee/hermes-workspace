"""Korean search for hermes: places, local buzz, opening hours, and a Korean web index.

Three sources, each carrying something the others cannot:

  Kakao 로컬     a real place_url, a phone number, a category filter, 45 results
  Naver 지역     a map.naver.com link and the shop's own booking/home page
  Google Places  opening hours -- neither Korean API returns them at all

Plus one provider rather than a fourth tool: web_search itself routes Hangul
queries to Daum. The model learns nothing new and every existing web_search call
in the daemon's prompts gets the Korean index for free.

No 최저가 tool. Naver's 쇼핑 검색 API was retired 2026-07-31 with no replacement
(measured: 404 SE05, while news.json answers 200 to the same request shape), so
prices go through web_search/web_extract like any other page.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict

from . import gplaces, kakao, naver
from ._util import env

# Registered into the existing `web` toolset, not a new one. `web` is already in
# the KakaoTalk daemon's --toolsets allowlist; an unknown name is dropped with a
# one-line "ignoring unknown --toolsets entries" and the tools never appear.
TOOLSET = "web"


def _json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _needs(*keys: str) -> Callable[[], bool]:
    """check_fn over env only -- the picker calls it on every paint, no network."""
    return lambda: all(env(k) for k in keys)


KAKAO_PLACE_SCHEMA = {
    "name": "kakao_place_search",
    "description": (
        "Find real places in Korea (restaurants, cafes, shops, stations) from Kakao Map. "
        "Use this for any 맛집/식당/카페/가게/장소 question. Returns the place's name, category, "
        "road address, phone number, coordinates, and a real Kakao Map URL -- always give that "
        "URL as the link instead of writing one yourself. Does NOT return opening hours: call "
        "place_hours for those. At most 45 places exist for any query."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search words, usually a place plus what you want, e.g. '성수동 파스타'.",
            },
            "category": {
                "type": "string",
                "description": (
                    "Optional Kakao category filter. Pass FD6 for restaurants (맛집/식당) and CE7 for "
                    "cafes -- it sharpens results a lot. Others: "
                    + ", ".join(f"{code}={label}" for code, label in sorted(kakao.CATEGORY_CODES.items()))
                ),
                "enum": sorted(kakao.CATEGORY_CODES),
            },
            "lon": {"type": "number", "description": "Optional centre longitude. Pass with lat to sort by distance."},
            "lat": {"type": "number", "description": "Optional centre latitude. Pass with lon to sort by distance."},
            "radius_m": {
                "type": "integer",
                "description": "Optional search radius in metres around lon/lat. Max 20000.",
                "minimum": 0, "maximum": kakao.RADIUS_MAX_M,
            },
            "size": {
                "type": "integer", "description": "How many places to return. Defaults to 5.",
                "minimum": 1, "maximum": 15, "default": 5,
            },
        },
        "required": ["query"],
    },
}

NAVER_LOCAL_SCHEMA = {
    "name": "naver_local_search",
    "description": (
        "Find a Korean place in Naver's local directory -- the map most people in Korea actually use. "
        "Returns a map.naver.com link and, when the shop has one, its own homepage or booking page "
        "(catchtable and the like), which Kakao does not provide. Use it alongside kakao_place_search "
        "when someone wants a Naver map link or a reservation page. Returns no phone number and at "
        "most 5 places."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search words, e.g. '성수동 파스타'."},
            "sort": {
                "type": "string", "enum": ["comment", "random"], "default": "comment",
                "description": "comment = most-reviewed first (default). random = relevance.",
            },
            "display": {
                "type": "integer", "description": "How many places to return (max 5).",
                "minimum": 1, "maximum": 5, "default": 5,
            },
        },
        "required": ["query"],
    },
}

NAVER_BLOG_SCHEMA = {
    "name": "naver_blog_search",
    "description": (
        "Read recent Naver blog posts about something. In Korea blog reviews are where real opinion "
        "about a restaurant lives, so use this to judge whether a place is any good, whether it is "
        "still open, or what is new. Returns titles, summaries, links and post dates, newest first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to read about, e.g. '성수동 파스타 맛집'."},
            "sort": {
                "type": "string", "enum": ["date", "sim"], "default": "date",
                "description": "date = newest first (default, stays on topic). sim = relevance, drifts.",
            },
            "display": {
                "type": "integer", "description": "How many posts to return. Defaults to 5.",
                "minimum": 1, "maximum": 20, "default": 5,
            },
        },
        "required": ["query"],
    },
}

PLACE_HOURS_SCHEMA = {
    "name": "place_hours",
    "description": (
        "Opening hours, whether a place is open right now, and its rating. This is the only tool that "
        "knows opening hours -- the Korean place APIs do not carry them. Pass the place name you got "
        "from kakao_place_search, ideally with its neighbourhood. Copy the returned schedule as-is and "
        "read 'open now' off the flag; do not work out the weekday yourself."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Place name, ideally with area, e.g. '성수동 온량'."},
            "limit": {
                "type": "integer", "description": "How many candidates to return. Defaults to 2.",
                "minimum": 1, "maximum": 5, "default": 2,
            },
        },
        "required": ["query"],
    },
}


def register(ctx) -> None:
    """Plugin entry point: one web_search backend and four Korean tools."""
    ctx.register_web_search_provider(kakao.DaumWebSearchProvider())

    ctx.register_tool(
        name="kakao_place_search", toolset=TOOLSET, schema=KAKAO_PLACE_SCHEMA,
        handler=lambda args, **kw: _json(kakao.place_search(
            args.get("query", ""), category=args.get("category"),
            lon=args.get("lon"), lat=args.get("lat"),
            radius_m=args.get("radius_m"), size=args.get("size", 5))),
        check_fn=_needs(kakao.KEY), requires_env=[kakao.KEY], emoji="📍")

    ctx.register_tool(
        name="naver_local_search", toolset=TOOLSET, schema=NAVER_LOCAL_SCHEMA,
        handler=lambda args, **kw: _json(naver.local_search(
            args.get("query", ""), sort=args.get("sort", "comment"),
            display=args.get("display", 5))),
        check_fn=_needs(naver.ID_KEY, naver.SECRET_KEY),
        requires_env=[naver.ID_KEY, naver.SECRET_KEY], emoji="🗺️")

    ctx.register_tool(
        name="naver_blog_search", toolset=TOOLSET, schema=NAVER_BLOG_SCHEMA,
        handler=lambda args, **kw: _json(naver.blog_search(
            args.get("query", ""), sort=args.get("sort", "date"),
            display=args.get("display", 5))),
        check_fn=_needs(naver.ID_KEY, naver.SECRET_KEY),
        requires_env=[naver.ID_KEY, naver.SECRET_KEY], emoji="📝")

    ctx.register_tool(
        name="place_hours", toolset=TOOLSET, schema=PLACE_HOURS_SCHEMA,
        handler=lambda args, **kw: _json(gplaces.place_hours(
            args.get("query", ""), limit=args.get("limit", 2))),
        check_fn=_needs(gplaces.KEY), requires_env=[gplaces.KEY], emoji="🕐")
