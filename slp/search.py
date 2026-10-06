"""검색 실행: 조건 -> 출처별 수집 -> 공통 필터 -> 실거래 비교 -> 점수 -> 저장."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from . import filtering, market, scoring, store
from .criteria import SOURCES, Criteria
from .http import Client
from .models import LAND_GROUP
from .sources import SourceResult, get_collector
from .sources import molit

log = logging.getLogger("slp")
KST = ZoneInfo("Asia/Seoul")
MAX_MARKET_SIGUNGU = 30  # 실거래가 API 호출량 보호


def run(c: Criteria, env: dict, issue: int | None = None, data_dir: Path = store.DATA_DIR,
        now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(KST)
    client = Client()
    results: list[SourceResult] = []
    for name in c.sources:
        log.info("수집 시작: %s", SOURCES[name])
        try:
            r = get_collector(name)(c, client, env)
        except Exception as e:  # 한 출처의 예기치 못한 오류가 전체를 막지 않게
            log.exception("%s 수집 오류", name)
            r = SourceResult(name, ok=False, message=f"오류: {e}")
        log.info("%s: %s", SOURCES[name], r.message)
        results.append(r)

    listings = filtering.apply(c, [li for r in results for li in r.listings])

    trades, market_msg = [], "실거래가 비교 안 함"
    key = env.get("DATA_GO_KR_KEY")
    if c.market_months and key:
        gus = c.sigungu_list()[:MAX_MARKET_SIGUNGU]
        want_land = not c.land_types or any(t in LAND_GROUP for t in c.land_types)
        want_house = not c.land_types or any("주택" in t for t in c.land_types)
        trades, errs = molit.fetch(client, key, gus, c.market_months, want_land, want_house)
        market.compare(listings, trades)
        market_msg = f"실거래 {len(trades)}건 ({len(gus)}개 시군구, 최근 {c.market_months}개월)"
        if errs:
            market_msg += f", 실패 {len(errs)}건 (예: {errs[0]})"
    elif c.market_months:
        market_msg = "DATA_GO_KR_KEY가 없어 실거래가 비교를 건너뜀"

    score_msg = scoring.score_all(listings, env.get("KAKAO_REST_KEY"), client)
    listings.sort(key=lambda li: (li.score is None, -(li.score or 0), li.price_manwon or 0))

    sid = now.strftime("%Y%m%d-%H%M") + (f"-i{issue}" if issue else "")
    result = {
        "meta": {
            "id": sid,
            "title": c.title(),
            "created_at": now.isoformat(timespec="seconds"),
            "issue": issue,
            "criteria": c.to_dict(),
            "sources": [r.summary() for r in results],
            "market_message": market_msg,
            "score_message": score_msg,
            "counts": {"listings": len(listings), "trades": len(trades)},
        },
        "listings": [li.to_dict() for li in listings],
        "market": market.summarize(trades),
        "trades": [t.to_dict() for t in trades[:2000]],
    }
    store.save_search(result, data_dir)
    return result


def summary_markdown(result: dict, pages_url: str = "") -> str:
    m = result["meta"]
    lines = [f"### 🔎 검색 완료: {m['title']}", "",
             f"- 조건에 맞는 물건: **{m['counts']['listings']}건**",
             f"- {m['market_message']}", f"- {m['score_message']}", "", "| 출처 | 결과 |", "|---|---|"]
    for s in m["sources"]:
        lines.append(f"| {SOURCES.get(s['source'], s['source'])} | {'✅' if s['ok'] else '⚠️'} {s['message']} |")
    if pages_url:
        lines += ["", f"👉 [결과 보기]({pages_url}#search={m['id']})  (Pages 반영까지 1~2분 걸릴 수 있어요)"]
    top = result["listings"][:5]
    if top:
        lines += ["", "**상위 5건**", ""]
        for li in top:
            price = f"{li['price_manwon']:,}만원" if li["price_manwon"] else "금액 미상"
            area = f"{li['area_m2']:,.0f}㎡({li['area_pyeong']}평)" if li["area_m2"] else "면적 미상"
            score = f" · 점수 {li['score']}" if li["score"] is not None else ""
            lines.append(f"- [{li['title']}]({li['url']}) — {li['address']} · {li['land_type']} · {price} · {area}{score}")
    return "\n".join(lines)
