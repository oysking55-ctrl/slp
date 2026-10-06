"""법원경매정보 (courtauction.go.kr) — 공식 API가 없어 웹 화면이 쓰는 JSON 요청을 흉내 낸다.

⚠ 실험적 기능: 사이트 개편·해외 IP 차단 시 실패할 수 있다. 실패해도 다른 출처 결과는 저장된다.
응답 구조를 모를 때를 대비해 여러 후보 필드명을 확인하고, 파싱에 실패하면 원본 일부를 로그에 남긴다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re

from ..criteria import Criteria
from ..http import Client
from ..models import Listing, normalize_land_type, to_float, to_manwon
from ..regions import address_matches, find_sido
from . import SourceResult

log = logging.getLogger("slp")

BASE = "https://www.courtauction.go.kr"
SEARCH_URL = os.environ.get("COURT_SEARCH_URL", BASE + "/pgj/pgjsearch/searchControllerMain.on")
PAGE_SIZE = 40
MAX_PAGES = 15
DAYS_AHEAD = 60

# 응답 필드 후보 (사이트 버전에 따라 이름이 다르다)
F_CASE = ["srnSaNo", "userCsNo", "csNo", "printCsNo", "saNo"]
F_SEQ = ["maemulSer", "dspslGdsSeq", "mulNo", "gdsSeq"]
F_COURT = ["jiwonNm", "cortOfcNm", "cortNm"]
F_ADDR = ["printSt", "bgPlaceRdAllAddr", "rdnmAddr", "adongAddr", "hjguAddr", "addr", "st"]
F_USAGE = ["dspslUsgNm", "sclDspslGdsLstUsgNm", "mulBigo", "usgNm", "lclsUtilCd"]
F_APPRAISAL = ["gamevalAmt", "aeeEvlAmt", "apslAmt"]
F_MIN = ["minmaePrice", "lwsDspslPrc", "minBidPrc"]
F_DATE = ["maeGiil", "dspslDxdyYmd", "bidDxdyYmd", "dxdyYmd"]
F_FAILS = ["yuchalCnt", "flbdNcnt"]
F_AREA = ["areaList", "pjbBuldList", "objctArDts", "area"]
F_STATUS = ["mulStatcd", "dspslGdsStatNm", "statNm"]


def _pick(d: dict, keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _find_rows(data) -> list[dict]:
    """응답 JSON 안에서 '물건 목록'으로 보이는 가장 큰 dict 리스트를 찾는다."""
    best: list[dict] = []

    def walk(x):
        nonlocal best
        if isinstance(x, list) and x and all(isinstance(i, dict) for i in x):
            if any(_pick(i, F_ADDR + F_CASE) for i in x) and len(x) > len(best):
                best = x
            for i in x:
                walk(i)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)

    walk(data)
    return best


def parse_area(text: str) -> float | None:
    t = (text or "").replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)", t)
    return float(m.group(1)) if m else to_float(t)


def to_listing(row: dict) -> Listing:
    case = _pick(row, F_CASE)
    seq = _pick(row, F_SEQ) or "1"
    court = _pick(row, F_COURT)
    usage = _pick(row, F_USAGE)
    date = _pick(row, F_DATE)
    if re.fullmatch(r"\d{8}", date):
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    addr = re.sub(r"\s+", " ", _pick(row, F_ADDR)).strip()
    return Listing(
        source="court",
        source_id=f"{court}-{case}-{seq}",
        title=f"{court} {case}" + (f" ({usage})" if usage else ""),
        address=addr,
        land_type=normalize_land_type(usage),
        price_manwon=to_manwon(_pick(row, F_MIN), "won"),
        appraisal_manwon=to_manwon(_pick(row, F_APPRAISAL), "won"),
        area_m2=parse_area(_pick(row, F_AREA)),
        url=BASE,  # 개편된 사이트는 직접 링크가 안 되어 사건번호로 검색해야 한다
        deadline=date,
        status=_pick(row, F_STATUS),
        failed_bids=int(to_float(_pick(row, F_FAILS)) or 0),
        extra={"법원": court, "사건번호": case, "물건번호": seq, "용도": usage},
    )


def build_payload(c: Criteria, page: int, today: dt.date) -> dict:
    s = find_sido(c.sido) or {}
    end = today + dt.timedelta(days=DAYS_AHEAD)
    return {
        "dma_pageInfo": {"pageNo": page, "pageSize": PAGE_SIZE, "bfPageNo": "", "startRowNo": "",
                         "totalCnt": "", "totalYn": "Y", "groupTotalCount": ""},
        "dma_srchGdsDtlSrchInfo": {
            "statNum": 1, "pgmId": "PGJ151F01", "cortStDvs": "1",
            "bidDvsCd": "000331", "mvprpRletDvsCd": "00031R", "cortAuctnSrchCondCd": "0004601",
            "rprsAdongSdCd": s.get("code", ""), "rprsAdongSggCd": "", "rprsAdongEmdCd": "",
            "bidBgngYmd": today.strftime("%Y%m%d"), "bidEndYmd": end.strftime("%Y%m%d"),
            "lwsDspslPrcMin": str(c.price_min * 10000) if c.price_min else "",
            "lwsDspslPrcMax": str(c.price_max * 10000) if c.price_max else "",
            "objctArDtsMin": str(int(c.area_min_m2)) if c.area_min_m2 else "",
            "objctArDtsMax": str(int(c.area_max_m2)) if c.area_max_m2 else "",
            "aeeEvlAmtMin": "", "aeeEvlAmtMax": "", "flbdNcntMin": "", "flbdNcntMax": "",
            "lclDspslGdsLstUsgCd": "", "mclDspslGdsLstUsgCd": "", "sclDspslGdsLstUsgCd": "",
            "cortOfcCd": "", "csNo": "",
        },
    }


def collect(c: Criteria, client: Client, env: dict) -> SourceResult:
    res = SourceResult("court")
    today = dt.date.today()
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json",
               "Origin": BASE, "Referer": BASE + "/pgj/index.on", "SC-Userid": "NONUSER",
               "SC-Pgmid": "PGJ151F01"}
    try:
        client.get(BASE + "/pgj/index.on")  # 세션 쿠키
    except Exception as e:
        res.ok, res.message = False, f"법원경매 사이트 접속 실패 (해외 IP 차단 가능): {e}"
        log.warning(res.message)
        return res
    rows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        try:
            r = client.post(SEARCH_URL, data=json.dumps(build_payload(c, page, today)), headers=headers)
            data = r.json()
        except Exception as e:
            res.ok, res.message = False, f"법원경매 검색 실패: {e}"
            log.warning(res.message)
            break
        page_rows = _find_rows(data)
        if not page_rows:
            if page == 1:
                res.ok = False
                res.message = "법원경매 응답에서 물건 목록을 찾지 못함 (사이트 구조 변경 가능)"
                log.warning("%s. 응답 일부: %s", res.message, json.dumps(data, ensure_ascii=False)[:1500])
            break
        rows += page_rows
        if len(page_rows) < PAGE_SIZE:
            break
    res.fetched = len(rows)
    sigungu = c.sigungu_list() if c.sigungu else None
    seen = set()
    for row in rows:
        li = to_listing(row)
        if li.id in seen or not address_matches(li.address, c.sido, sigungu):
            continue
        seen.add(li.id)
        li.sido = c.sido
        res.listings.append(li)
    if rows and res.listings == [] and res.fetched:
        log.info("법원경매 첫 행 예시: %s", json.dumps(rows[0], ensure_ascii=False)[:800])
    if res.ok:
        res.message = f"경매 물건 {len(res.listings)}건 (향후 {DAYS_AHEAD}일 매각기일)"
    return res
