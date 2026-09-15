"""Naver 지역 + 블로그 (개발자센터 검색 API).

ponytail: base, path and headers live in _call() alone. This install is on the
개발자센터 path, which stops working 2027-06-30 -- the 검색 API moved to NCP's
NAVER API HUB (신규 신청은 2026-07-31 에 이미 막혔고, 이 키는 그 전 등록분이라
유예 대상이다). Migrating means changing three things in this one function:

    base    https://openapi.naver.com   ->  https://naverapihub.apigw.ntruss.com
    path    /v1/search/local.json       ->  /search/v1/local
    headers X-Naver-Client-Id/-Secret   ->  X-NCP-APIGW-API-KEY-ID/-KEY

쇼핑·책·전문자료 검색은 2026-07-31 에 종료됐고 대체 API 가 없다 (측정: 404
SE05, 같은 요청 형태로 news.json 은 200). 최저가 툴이 여기 없는 이유다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from ._util import clamp, clean, env, err, get_json, memoized, require

ID_KEY, SECRET_KEY = "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"
BASE = "https://openapi.naver.com"
NAVER_MAP_SEARCH = "https://map.naver.com/p/search/"


def _call(path: str, who: str, params: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "X-Naver-Client-Id": env(ID_KEY),
        "X-Naver-Client-Secret": env(SECRET_KEY),
    }
    return get_json(f"{BASE}{path}", who=who, headers=headers, params=params)


def _region_token(road_address: str) -> str:
    """The narrowest 구/군/시 in a road address, for disambiguating a map search.

    Naver's 지역 API has no place id, so the map link is a *search* URL -- and a
    bare 상호 lands on whichever branch Naver likes. Adding the 구 pins it.

    구/군 wins over 시 because addresses lead with the province: taking the first
    token that merely ends in 시 turns "서울특별시 성동구 …" into "서울특별시",
    which narrows nothing. A 시 is only used when there is no 구/군 under it
    (경기도 이천시), and the 특별시/광역시 forms are never it.
    """
    tokens = (road_address or "").split()
    for token in tokens:
        if len(token) > 1 and token.endswith(("구", "군")):
            return token
    for token in tokens:
        if len(token) > 2 and token.endswith("시") and not token.endswith(("특별시", "광역시", "자치시")):
            return token
    return ""


def _map_url(name: str, road_address: str) -> str:
    region = _region_token(road_address)
    return NAVER_MAP_SEARCH + quote(f"{name} {region}".strip())


def local_search(query: str, sort: str = "comment", display: int = 5) -> Dict[str, Any]:
    for key in (ID_KEY, SECRET_KEY):
        missing = require(key, "네이버 지역 검색")
        if missing:
            return missing
    if not (query or "").strip():
        return err("query 가 비었다.")
    if sort not in ("comment", "random"):
        sort = "comment"

    # display maxes at 5 and start maxes at 1 -- five results is the ceiling for
    # this API, there is no paging past it.
    params = {"query": query.strip(), "display": clamp(display, 1, 5, 5), "sort": sort}

    def fetch() -> Dict[str, Any]:
        data = _call("/v1/search/local.json", "네이버 지역 검색", params)
        if "error" in data:
            return data
        places = []
        for item in data.get("items") or []:
            name = clean(item.get("title", ""))
            road = item.get("roadAddress", "")
            row: Dict[str, Any] = {
                "name": name,
                "category": item.get("category", ""),
                "address": road or item.get("address", ""),
                "naver_map_url": _map_url(name, road),
            }
            # The business's own site -- booking pages (catchtable), homepages,
            # instagram. Kakao has no equivalent field. Often empty.
            if item.get("link"):
                row["homepage"] = item["link"]
            # mapx/mapy are WGS84 scaled by 1e7 despite the doc's KATEC example.
            for src, dst in (("mapx", "lon"), ("mapy", "lat")):
                try:
                    row[dst] = int(item[src]) / 1e7
                except (KeyError, TypeError, ValueError):
                    pass
            places.append(row)
        return {
            "places": places,
            # telephone is deliberately dropped: it came back empty on every row
            # measured and the official doc's own example shows it empty. Handing
            # the model an empty string invites it to promise a phone number.
            "phone_note": "이 API 는 전화번호를 주지 않는다. 전화가 필요하면 kakao_place_search 를 써라.",
        }

    return memoized(("naver_local", tuple(sorted(params.items()))), fetch)


def blog_search(query: str, sort: str = "date", display: int = 5) -> Dict[str, Any]:
    for key in (ID_KEY, SECRET_KEY):
        missing = require(key, "네이버 블로그 검색")
        if missing:
            return missing
    if not (query or "").strip():
        return err("query 가 비었다.")
    # date, not the API's sim default: sim drifts off-query (measured -- the
    # second hit for a 성수동 파스타 query was a 평생학습관 notice), date stayed
    # on it for all five.
    if sort not in ("date", "sim"):
        sort = "date"

    params = {"query": query.strip(), "display": clamp(display, 1, 20, 5), "sort": sort}

    def fetch() -> Dict[str, Any]:
        data = _call("/v1/search/blog.json", "네이버 블로그 검색", params)
        if "error" in data:
            return data
        return {"posts": [
            {
                "title": clean(item.get("title", "")),
                "summary": clean(item.get("description", "")),
                "url": item.get("link", ""),
                "blogger": item.get("bloggername", ""),
                "posted": item.get("postdate", ""),
            }
            for item in data.get("items") or []
        ]}

    return memoized(("naver_blog", tuple(sorted(params.items()))), fetch)
