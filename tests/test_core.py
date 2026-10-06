from pathlib import Path

import pytest

from slp import filtering, market, regions, scoring
from slp.criteria import Criteria, parse_issue_body, parse_money
from slp.http import xml_items
from slp.models import Listing, normalize_land_type
from slp.sources import court, molit, onbid

FIX = Path(__file__).parent / "fixtures"


def test_parse_issue_body():
    c = parse_issue_body((FIX / "issue_body.md").read_text(encoding="utf-8"))
    assert c.name == "홍천 전원주택 후보"
    assert c.sido == "강원특별자치도"
    assert c.sigungu == ["홍천군", "횡성군"]
    assert c.land_types == ["대지", "단독주택", "전원주택"]
    assert c.area_min_m2 == pytest.approx(330.58, abs=0.01)  # 100평
    assert c.price_min is None and c.price_max == 35000
    assert c.sources == ["onbid", "naver"]
    assert c.market_months == 12
    assert [g.code for g in c.sigungu_list()] == ["51720", "51730"]


def test_issue_body_errors():
    with pytest.raises(ValueError, match="시도"):
        parse_issue_body("### 시도\n\n_No response_\n")
    with pytest.raises(ValueError):
        Criteria(sido="강원도", price_min=5, price_max=1)


@pytest.mark.parametrize("text,expected", [
    ("3억", 30000), ("3억 5000", 35000), ("1.5억", 15000), ("5천만", 5000), ("12,000", 12000), ("8000만원", 8000)])
def test_parse_money(text, expected):
    assert parse_money(text) == expected


def test_regions():
    gus = regions.resolve("경기", ["수원시", "양평군"])
    assert [g.name for g in gus][:1] == ["수원시 장안구"] and gus[-1].name == "양평군"
    assert regions.find_sido("강원도")["code"] == "51"
    assert regions.address_matches("강원도 홍천군 내면", "강원특별자치도", regions.resolve("강원", ["홍천군"]))
    assert not regions.address_matches("강원도 춘천시", "강원특별자치도", regions.resolve("강원", ["홍천군"]))
    with pytest.raises(ValueError):
        regions.resolve("강원", ["없는군"])


@pytest.mark.parametrize("text,expected", [
    ("토지 / 대지", "대지"), ("대", "대지"), ("전", "전"), ("토지 / 임야", "임야"), ("단독/다가구", "단독주택"),
    ("주거용건물 / 단독주택", "단독주택"), ("전원주택", "전원주택"), ("토지", "토지(지목미상)"), ("상가", "기타")])
def test_normalize_land_type(text, expected):
    assert normalize_land_type(text) == expected


def test_molit_parse_skips_cancelled():
    items, _ = xml_items((FIX / "molit_land.xml").read_text(encoding="utf-8"))
    gu = regions.resolve("강원", ["홍천군"])[0]
    trades = molit.parse_land(items, gu)
    assert len(trades) == 3
    assert trades[0].price_manwon == 12000 and trades[0].land_type == "대지"
    assert trades[0].deal_date == "2026-05-03"


def test_xml_error():
    bad = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
           "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>")
    with pytest.raises(ValueError, match="SERVICE_KEY"):
        xml_items(bad)


def test_recent_months():
    import datetime as dt
    assert molit.recent_months(3, dt.date(2026, 2, 10)) == ["202602", "202601", "202512"]


def test_onbid_collect(monkeypatch):
    text = (FIX / "onbid.xml").read_text(encoding="utf-8")

    class FakeClient:
        def get(self, url, params=None, **kw):
            class R:
                pass
            r = R()
            r.text = text
            return r

    c = Criteria(sido="강원특별자치도", sigungu=["홍천군"])
    res = onbid.collect(c, FakeClient(), {"DATA_GO_KR_KEY": "x"})
    assert res.ok and res.fetched == 3
    assert len(res.listings) == 1  # 자동차·다른 시군구 제외
    li = res.listings[0]
    assert li.price_manwon == 4500 and li.appraisal_manwon == 6400
    assert li.area_m2 == 1322 and li.land_type == "대지" and li.failed_bids == 2
    assert "cltrNo=333" in li.url
    assert li.deadline == "2026-10-22 17:00"


def test_onbid_without_key():
    res = onbid.collect(Criteria(sido="강원"), None, {})
    assert not res.ok and "DATA_GO_KR_KEY" in res.message


def test_court_row_parsing_and_finder():
    data = {"data": {"dma_pageInfo": {"totalCnt": 1}, "dlt_srchResult": [
        {"jiwonNm": "춘천지방법원", "srnSaNo": "2025타경1234", "maemulSer": "1",
         "printSt": "강원특별자치도 홍천군 내면  창촌리 1", "dspslUsgNm": "대지",
         "gamevalAmt": "100000000", "minmaePrice": "49000000", "maeGiil": "20261103",
         "yuchalCnt": "2", "areaList": "대 660㎡"}]}}
    rows = court._find_rows(data)
    li = court.to_listing(rows[0])
    assert li.id == "court:춘천지방법원-2025타경1234-1"
    assert li.price_manwon == 4900 and li.appraisal_manwon == 10000
    assert li.area_m2 == 660 and li.deadline == "2026-11-03" and li.land_type == "대지"
    assert li.address == "강원특별자치도 홍천군 내면 창촌리 1"


def _li(**kw):
    base = dict(source="onbid", source_id="1", title="t", address="강원특별자치도 홍천군 내면 1",
                land_type="대지", price_manwon=5000, area_m2=500.0)
    base.update(kw)
    return Listing(**base)


def test_filtering_keeps_unknowns_and_generic_land():
    c = Criteria(sido="강원", land_types=["대지"], area_min_m2=300, price_max=10000)
    items = [_li(), _li(source_id="2", area_m2=100), _li(source_id="3", price_manwon=20000),
             _li(source_id="4", area_m2=None), _li(source_id="5", land_type="토지(지목미상)"),
             _li(source_id="6", land_type="임야")]
    out = filtering.apply(c, items)
    assert [li.source_id for li in out] == ["1", "4", "5"]
    assert out[1].extra["확인 필요"] == "면적 미확인"


def test_market_compare():
    items, _ = xml_items((FIX / "molit_land.xml").read_text(encoding="utf-8"))
    trades = molit.parse_land(items, regions.resolve("강원", ["홍천군"])[0])
    li = _li(price_manwon=5000, area_m2=500)  # 10만원/㎡, 중위 25만원/㎡
    market.compare([li], trades)
    assert li.market["ratio"] == 0.4 and li.market["samples"] == 3
    rows = market.summarize(trades)
    assert rows[0]["median_per_m2"] == 25.0


def test_scoring_math():
    assert scoring.points(1000, 3, 15) == 1.0
    assert scoring.points(15000, 3, 15) == 0.0
    assert scoring.points(9000, 3, 15) == pytest.approx(0.5)
    assert scoring.points(None, 3, 15) == 0.0
    f = [{"id": "a", "near_km": 1, "far_km": 3, "weight": 30}, {"id": "b", "near_km": 1, "far_km": 3, "weight": 10}]
    assert scoring.total_score({"a": 500, "b": None}, f) == 75.0
    assert scoring.score_all([], None, None).startswith("KAKAO_REST_KEY")


def test_scoring_config_within_kakao_radius():
    for f in scoring.load_config()["factors"]:
        assert f["far_km"] * 1000 <= scoring.SEARCH_RADIUS


def test_run_pipeline_offline(tmp_path, monkeypatch):
    """키 없이도 실행되고 결과 파일·인덱스가 생긴다."""
    from slp import search
    from slp.sources import SourceResult

    def fake_collect(c, client, env):
        return SourceResult("onbid", listings=[_li(), _li(source_id="2", land_type="임야")], fetched=2)

    monkeypatch.setattr(search, "get_collector", lambda name: fake_collect)
    c = Criteria(sido="강원", sigungu=["홍천군"], land_types=["대지"], sources=["onbid"])
    result = search.run(c, {}, issue=7, data_dir=tmp_path)
    assert result["meta"]["counts"]["listings"] == 1
    assert (tmp_path / "searches" / f"{result['meta']['id']}.json").exists()
    import json
    idx = json.loads((tmp_path / "searches" / "index.json").read_text(encoding="utf-8"))
    assert idx[0]["issue"] == 7
    md = search.summary_markdown(result, "https://x.github.io/slp/")
    assert "1건" in md and "#search=" in md
