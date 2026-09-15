"""Google Places (New) -- the only source here that knows opening hours.

Neither 카카오 로컬 nor 네이버 지역 returns them; this is not an implementation
gap, it is what those APIs are. Places is a billed SKU, so the field mask stays
narrow on purpose -- widening it moves the call into a higher tier.
"""

from __future__ import annotations

from typing import Any, Dict

from ._util import clamp, env, err, memoized, post_json, require

KEY = "GOOGLE_PLACES_API_KEY"
URL = "https://places.googleapis.com/v1/places:searchText"

# Narrow on purpose (see module docstring). Adding reviews or photos here is a
# pricing decision, not a formatting one.
FIELD_MASK = ",".join((
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.regularOpeningHours.weekdayDescriptions",
    "places.currentOpeningHours.openNow",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
))


def place_hours(query: str, limit: int = 2) -> Dict[str, Any]:
    missing = require(KEY, "구글 영업시간 조회")
    if missing:
        return missing
    if not (query or "").strip():
        return err("query 가 비었다.")

    body = {
        "textQuery": query.strip(),
        "languageCode": "ko",
        "regionCode": "KR",
        "maxResultCount": clamp(limit, 1, 5, 2),
    }

    def fetch() -> Dict[str, Any]:
        data = post_json(
            URL, who="구글 Places",
            headers={"X-Goog-Api-Key": env(KEY), "X-Goog-FieldMask": FIELD_MASK},
            json_body=body,
        )
        if "error" in data:
            return data
        places = []
        for place in data.get("places") or []:
            row: Dict[str, Any] = {
                "name": (place.get("displayName") or {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "map_url": place.get("googleMapsUri", ""),
            }
            if place.get("nationalPhoneNumber"):
                row["phone"] = place["nationalPhoneNumber"]
            hours = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions")
            if hours:
                row["hours"] = hours
            open_now = (place.get("currentOpeningHours") or {}).get("openNow")
            if open_now is not None:
                row["open_now"] = open_now
            if place.get("rating") is not None:
                row["rating"] = place["rating"]
                row["rating_count"] = place.get("userRatingCount")
            places.append(row)
        return {
            "places": places,
            # The model must not do weekday arithmetic. It got this wrong before
            # in voice-agent (told a caller "we're open till 8" on a closed
            # Sunday), which is why src/store.py computes hours in code there.
            # Here the fix is cheaper: hand over both the written schedule and a
            # ready-made boolean, and say so.
            "hours_note": ("hours 는 그대로 옮겨 적어라. 오늘이 무슨 요일인지 직접 계산하지 마라. "
                           "지금 영업 중인지는 open_now 만 보고 말해라."),
        }

    return memoized(("gplaces", body["textQuery"], body["maxResultCount"]), fetch)
