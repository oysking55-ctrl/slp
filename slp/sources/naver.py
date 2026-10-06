"""네이버 부동산 (모바일 웹이 쓰는 비공식 JSON) — 토지·단독/다가구·전원주택 매매.

⚠ 비공식 경로이며 네이버 이용약관은 자동 수집을 제한한다. 개인 참고용으로 검색할 때만
  체크하고, 요청 간격을 길게 둔다. 차단(429/403)되면 조용히 실패 처리한다.
"""
from __future__ import annotations

import logging

from ..criteria import Criteria
from ..http import Client
from ..models import Listing, normalize_land_type, to_float
from . import SourceResult

log = logging.getLogger("slp")

BASE = "https://m.land.naver.com"
REAL_ESTATE_TYPES = "TJ:DDDGG:JWJT"  # 토지, 단독/다가구, 전원주택
MAX_PAGES = 5
SPAN = (0.12, 0.16)  # 시군구 중심 기준 위도/경도 반경 (대략)


def to_listing(a: dict, sido: str, gu_name: str) -> Listing:
    area = to_float(a.get("spc1")) or to_float(a.get("spc2"))
    desc = a.get("atclFetrDesc") or ""
    return Listing(
        source="naver",
        source_id=str(a.get("atclNo")),
        title=(a.get("atclNm") or a.get("rletTpNm") or "매물") + (f" - {desc}" if desc else ""),
        address=f"{sido} {gu_name}",
        land_type=normalize_land_type(a.get("rletTpNm")),
        price_manwon=int(a["prc"]) if str(a.get("prc", "")).isdigit() else None,
        area_m2=area,
        url=f"{BASE}/article/info/{a.get('atclNo')}",
        sido=sido,
        sigungu=gu_name,
        lat=to_float(a.get("lat")),
        lng=to_float(a.get("lng")),
        status=a.get("atclCfmYmd", ""),
        extra={"중개사": a.get("rltrNm", ""), "태그": ", ".join(a.get("tagList") or []),
               "유형": a.get("rletTpNm", "")},
    )


def collect(c: Criteria, client: Client, env: dict) -> SourceResult:
    res = SourceResult("naver")
    headers = {"Referer": BASE + "/", "Accept": "application/json"}
    slow = Client(min_interval=1.5)
    slow.s.headers.update(client.s.headers)
    gus = c.sigungu_list()
    sido_code = gus[0].sido_code if gus else ""
    try:
        regions = slow.get(f"{BASE}/map/getRegionList", params={"cortarNo": sido_code + "00000000"},
                           headers=headers).json()["result"]["list"]
    except Exception as e:
        res.ok, res.message = False, f"네이버 지역 조회 실패 (차단 가능): {e}"
        log.warning(res.message)
        return res
    centers = {r.get("CortarNo"): (to_float(r.get("MapYCrdn")), to_float(r.get("MapXCrdn")),
                                   r.get("CortarNm")) for r in regions}
    seen = set()
    for gu in gus:
        cortar = gu.cortar_no
        center = centers.get(cortar) or centers.get(gu.code[:4] + "0" + "00000")  # 구가 있는 시는 시 단위
        if not center or center[0] is None:
            log.info("네이버: %s 좌표 없음, 건너뜀", gu.full_name)
            continue
        lat, lng, _ = center
        for page in range(1, MAX_PAGES + 1):
            params = {"rletTpCd": REAL_ESTATE_TYPES, "tradTpCd": "A1", "z": 11,
                      "lat": lat, "lon": lng, "btm": lat - SPAN[0], "top": lat + SPAN[0],
                      "lft": lng - SPAN[1], "rgt": lng + SPAN[1], "cortarNo": cortar, "page": page}
            if c.price_min:
                params["dprcMin"] = c.price_min
            if c.price_max:
                params["dprcMax"] = c.price_max
            try:
                data = slow.get(f"{BASE}/cluster/ajax/articleList", params=params, headers=headers).json()
            except Exception as e:
                res.ok, res.message = False, f"네이버 매물 조회 실패 (차단 가능): {e}"
                log.warning(res.message)
                return res
            body = data.get("body") or []
            res.fetched += len(body)
            for a in body:
                li = to_listing(a, c.sido, gu.name)
                if li.id not in seen:
                    seen.add(li.id)
                    res.listings.append(li)
            if not data.get("more"):
                break
    res.message = f"일반 매물 {len(res.listings)}건"
    return res
