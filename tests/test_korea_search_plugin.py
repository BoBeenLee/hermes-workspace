"""Tests for the korea_search plugin.

``agent.*`` and ``plugins.web.*`` live in the hermes-agent install, not in this
repo, so the two symbols the plugin imports are stubbed with their real
signatures. Every test drives the code through a fake httpx client -- no
network, no keys.
"""

import json
import sys
import types
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _install_agent_stub():
    """``agent.web_search_provider``: the ABC plus the config-aware env reader."""
    agent = sys.modules.setdefault("agent", types.ModuleType("agent"))
    agent.__path__ = []  # noqa: SLF001 - make it a package so submodules import

    module = types.ModuleType("agent.web_search_provider")

    class WebSearchProvider:
        def supports_search(self):
            return True

        def supports_extract(self):
            return False

        def is_keyless_available(self):
            return False

    module.WebSearchProvider = WebSearchProvider
    module.get_provider_env = lambda name: ""  # patched per test
    sys.modules["agent.web_search_provider"] = module
    agent.web_search_provider = module
    return module


def _install_httpx_stub():
    """``httpx`` is a hermes-agent dependency, not one of this repo's. Every test
    patches ``_util.httpx.Client`` with its own fake, so a module carrying the
    name is enough and the suite stays runnable on a bare checkout."""
    if "httpx" not in sys.modules:
        module = types.ModuleType("httpx")
        module.Client = object
        sys.modules["httpx"] = module


_AGENT = _install_agent_stub()
_install_httpx_stub()
sys.path.insert(0, str(REPO))

from plugins.korea_search import _util, gplaces, kakao, naver  # noqa: E402
import plugins.korea_search as plugin  # noqa: E402

KEYS = {
    kakao.KEY: "kakao-key",
    naver.ID_KEY: "naver-id",
    naver.SECRET_KEY: "naver-secret",
    gplaces.KEY: "google-key",
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for ``httpx.Client``; records the one request it is given."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._response


class KoreaSearchTest(unittest.TestCase):
    def setUp(self):
        _util._memo.clear()
        self._env = unittest.mock.patch.object(
            _AGENT, "get_provider_env", lambda name: KEYS.get(name, ""))
        self._env.start()
        self.addCleanup(self._env.stop)

    def _serve(self, payload, status=200):
        client = FakeClient(FakeResponse(payload, status))
        patcher = unittest.mock.patch.object(_util.httpx, "Client", client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    # --- key gating ------------------------------------------------------
    def test_tools_are_hidden_without_their_keys(self):
        """check_fn must be env-only and false when a key is missing."""
        with unittest.mock.patch.object(_AGENT, "get_provider_env", lambda name: ""):
            self.assertFalse(plugin._needs(kakao.KEY)())
            self.assertFalse(plugin._needs(naver.ID_KEY, naver.SECRET_KEY)())
            self.assertFalse(kakao.DaumWebSearchProvider().is_available())
        self.assertTrue(plugin._needs(kakao.KEY)())
        self.assertTrue(kakao.DaumWebSearchProvider().is_available())

    def test_missing_key_is_an_error_not_an_exception(self):
        with unittest.mock.patch.object(_AGENT, "get_provider_env", lambda name: ""):
            self.assertIn("error", kakao.place_search("성수동 파스타"))

    # --- shaping ---------------------------------------------------------
    def test_place_search_keeps_the_real_map_url_and_drops_empty_phone(self):
        self._serve({
            "documents": [
                {"place_name": "온량", "category_name": "음식점 > 양식", "phone": "02-6403-3643",
                 "address_name": "서울 성동구 성수동1가 668-54",
                 "road_address_name": "서울 성동구 서울숲4길 26-10",
                 "place_url": "http://place.map.kakao.com/1493852185",
                 "x": "127.043440031512", "y": "37.5469079011998", "distance": ""},
                {"place_name": "이름만", "category_name": "음식점", "phone": "",
                 "address_name": "", "road_address_name": "", "place_url": "http://place.map.kakao.com/1",
                 "x": "127.0", "y": "37.0", "distance": ""},
            ],
            "meta": {"total_count": 789, "pageable_count": 45, "is_end": False,
                     "same_name": {"keyword": "파스타", "region": ["서울 성동구 성수동2가"],
                                   "selected_region": "서울 성동구 성수동1가"}},
        })
        out = kakao.place_search("성수동 파스타", category="FD6")
        first, second = out["places"]
        self.assertEqual(first["map_url"], "http://place.map.kakao.com/1493852185")
        self.assertEqual(first["phone"], "02-6403-3643")
        self.assertAlmostEqual(first["lat"], 37.5469079011998)
        self.assertNotIn("phone", second)          # empty string must not reach the model
        self.assertNotIn("distance_m", first)      # absent without an x/y centre
        self.assertEqual(out["reachable_max"], 45)
        self.assertEqual(out["region_note"]["picked"], "서울 성동구 성수동1가")

    def test_place_search_rejects_an_unknown_category(self):
        out = kakao.place_search("성수동 파스타", category="ZZ9")
        self.assertIn("error", out)

    def test_naver_local_builds_a_map_url_and_never_returns_a_phone(self):
        self._serve({"items": [{
            "title": "성수<b>다락</b>", "link": "http://www.instagram.com/seongsudarak",
            "category": "음식점>양식", "description": "", "telephone": "",
            "address": "서울특별시 성동구 성수동2가 328-15 2층",
            "roadAddress": "서울특별시 성동구 뚝섬로9길 20 2층",
            "mapx": "1270562588", "mapy": "375398955",
        }]})
        row = naver.local_search("성수동 맛집")["places"][0]
        self.assertEqual(row["name"], "성수다락")                     # <b> stripped
        self.assertIn("map.naver.com/p/search/", row["naver_map_url"])
        self.assertIn("%EC%84%B1%EB%8F%99%EA%B5%AC", row["naver_map_url"])  # 성동구 pins the branch
        self.assertEqual(row["homepage"], "http://www.instagram.com/seongsudarak")
        self.assertAlmostEqual(row["lon"], 127.0562588)              # 1e7-scaled, not KATEC
        self.assertNotIn("phone", row)

    def test_region_token_prefers_the_narrowest_unit(self):
        """A leading 서울특별시 narrows nothing; the 구 is what pins the branch."""
        self.assertEqual(naver._region_token("서울특별시 성동구 뚝섬로9길 20"), "성동구")
        self.assertEqual(naver._region_token("경기도 성남시 분당구 판교역로 4"), "분당구")
        self.assertEqual(naver._region_token("경기도 이천시 부발읍 경충대로 2091"), "이천시")
        self.assertEqual(naver._region_token(""), "")

    def test_naver_local_omits_an_absent_homepage(self):
        self._serve({"items": [{"title": "소문난성수감자탕", "link": "", "category": "한식>감자탕",
                                "roadAddress": "서울특별시 성동구 연무장길 45",
                                "mapx": "1270543870", "mapy": "375428370"}]})
        self.assertNotIn("homepage", naver.local_search("감자탕")["places"][0])

    def test_blog_search_defaults_to_newest_first(self):
        client = self._serve({"items": [{"title": "<b>성수</b> 파스타", "description": "d",
                                         "link": "u", "bloggername": "b", "postdate": "20260915"}]})
        out = naver.blog_search("성수동 파스타 맛집")
        self.assertEqual(client.calls[0][2]["params"]["sort"], "date")
        self.assertEqual(out["posts"][0]["title"], "성수 파스타")

    def test_place_hours_hands_over_the_schedule_and_the_flag(self):
        self._serve({"places": [{
            "displayName": {"text": "온량"}, "formattedAddress": "서울특별시 성동구 서울숲4길 26-10",
            "nationalPhoneNumber": "02-6403-3643", "rating": 4.4, "userRatingCount": 427,
            "googleMapsUri": "https://maps.google.com/?cid=1",
            "regularOpeningHours": {"weekdayDescriptions": ["월요일: 오후 12:00~9:00"]},
            "currentOpeningHours": {"openNow": False},
        }]})
        out = gplaces.place_hours("성수동 온량")
        row = out["places"][0]
        self.assertEqual(row["hours"], ["월요일: 오후 12:00~9:00"])
        self.assertIs(row["open_now"], False)
        self.assertIn("직접 계산하지 마라", out["hours_note"])

    # --- the web_search provider ----------------------------------------
    def test_hangul_query_goes_to_daum(self):
        client = self._serve({"documents": [
            {"title": "<b>성수동</b> 파스타", "contents": "c &amp; c", "url": "https://example.kr"}]})
        out = kakao.DaumWebSearchProvider().search("성수동 파스타 맛집", limit=3)
        self.assertTrue(out["success"])
        self.assertIn("dapi.kakao.com/v2/search/web", client.calls[0][1])
        hit = out["data"]["web"][0]
        self.assertEqual(hit["title"], "성수동 파스타")
        self.assertEqual(hit["description"], "c & c")   # entities unescaped
        self.assertEqual(hit["position"], 1)

    def test_english_query_is_delegated_to_the_keyless_ring(self):
        ring = types.ModuleType("plugins.web.keyless_mcp")
        ring.search_with_failover = unittest.mock.Mock(
            return_value={"success": True, "data": {"web": []}})
        with unittest.mock.patch.dict(sys.modules, {
                "plugins.web": types.ModuleType("plugins.web"),
                "plugins.web.keyless_mcp": ring}):
            out = kakao.DaumWebSearchProvider().search("rust async runtime", limit=4)
        ring.search_with_failover.assert_called_once_with("daum", "rust async runtime", 4)
        self.assertTrue(out["success"])

    def test_english_query_falls_back_to_daum_when_the_ring_is_gone(self):
        """The private import is breakable by design; web_search must not go dark."""
        client = self._serve({"documents": [{"title": "t", "contents": "c", "url": "u"}]})
        with unittest.mock.patch.dict(sys.modules, {"plugins.web.keyless_mcp": None}):
            out = kakao.DaumWebSearchProvider().search("rust async runtime")
        self.assertTrue(out["success"])
        self.assertIn("dapi.kakao.com", client.calls[0][1])

    # --- failure handling ------------------------------------------------
    def test_quota_exhaustion_is_reported_not_raised(self):
        self._serve({"msg": "API limit has been exceeded.", "code": -10}, status=429)
        out = kakao.place_search("성수동 파스타")
        self.assertIn("한도", out["error"])
        self.assertIn("429", out["error"])

    def test_a_failure_is_not_memoized(self):
        """A 429 clears at midnight and a 500 is transient -- caching either would
        outlive the problem. Successes are cached; failures re-ask."""
        self._serve({"msg": "boom"}, status=500)
        kakao.place_search("성수동 파스타")
        self.assertEqual(_util._memo, {})

    def test_a_success_is_memoized_so_a_loop_costs_one_call(self):
        client = self._serve({"documents": [], "meta": {"total_count": 0, "pageable_count": 0}})
        for _ in range(3):
            kakao.place_search("성수동 파스타")
        self.assertEqual(len(client.calls), 1)


class RegistrationTest(unittest.TestCase):
    """register() must put every tool in the `web` toolset and nothing else."""

    def test_register_wires_one_provider_and_four_tools(self):
        ctx = unittest.mock.Mock()
        plugin.register(ctx)

        ctx.register_web_search_provider.assert_called_once()
        self.assertEqual(ctx.register_web_search_provider.call_args[0][0].name, "daum")

        names = [c.kwargs["name"] for c in ctx.register_tool.call_args_list]
        self.assertEqual(names, ["kakao_place_search", "naver_local_search",
                                 "naver_blog_search", "place_hours"])
        for call in ctx.register_tool.call_args_list:
            # A new toolset name would be silently dropped from the daemon's
            # --toolsets allowlist and the tools would never reach the model.
            self.assertEqual(call.kwargs["toolset"], "web")
            self.assertTrue(call.kwargs["requires_env"])
            self.assertEqual(call.kwargs["schema"]["name"], call.kwargs["name"])

    def test_handlers_return_json_text(self):
        ctx = unittest.mock.Mock()
        plugin.register(ctx)
        handler = ctx.register_tool.call_args_list[0].kwargs["handler"]
        with unittest.mock.patch.object(_AGENT, "get_provider_env", lambda name: ""):
            payload = json.loads(handler({"query": "성수동 파스타"}))
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
