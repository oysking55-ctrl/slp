"""온비드 캠코공매물건 (공공데이터포털 API).

필요: 환경변수 DATA_GO_KR_KEY
활용신청: '한국자산관리공사_온비드 캠코공매물건 조회서비스'
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlencode

from ..criteria import Criteria
from ..http import Client, xml_items
from ..models import Listing, normalize_land_type, to_float, to_manwon
from ..regions import address_matches, sido_variants
from . import SourceResult

log = logging.getLogger("slp")

URL = os.environ.get(
    "ONBID_URL",
    "http://openapi.onbid.co.kr/openapi/services/KamcoPblsalThingInquireSvc/getKamcoPbctCltrList",
)
DETAIL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralRealEstateDetail.do?"
PAGE_SIZE = 100
MAX_PAGES = 20


def parse_area(text: str) -> float | None:
    """'토지 330㎡, 건물 85.2㎡' 같은 문장에서 토지(첫) 면적을 찾는다."""
    if not text:
        return None
    t = text.replace(",", "")
    m = re.search(r"(?:토지|대지|면적)[^\d]{0,6}(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)", t)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²)", t)
    return float(m.group(1)) if m else None


def fmt_dtm(v: str) -> str:
    """'20261022170000' -> '2026-10-22 17:00'"""
    v = (v or "").strip()
    if re.fullmatch(r"\d{12,14}", v):
        return f"{v[:4]}-{v[4:6]}-{v[6:8]} {v[8:10]}:{v[10:12]}"
    return v


def to_listing(it: dict) -> Listing:
    category = it.get("CTGR_FULL_NM", "")
    address = it.get("LDNM_ADRS") or it.get("NMRD_ADRS") or ""
    q = {k: it.get(u, "") for k, u in [("cltrHstrNo", "CLTR_HSTR_NO"), ("cltrNo", "CLTR_NO"),
                                         ("plnmNo", "PLNM_NO"), ("pbctNo", "PBCT_NO"),
                                         ("scrnGrpCd", "SCRN_GRP_CD"), ("pbctCdtnNo", "PBCT_CDTN_NO")]}
    return Listing(
        source="onbid",
        source_id=f"{it.get('CLTR_NO', '')}-{it.get('PBCT_NO', '')}",
        title=it.get("CLTR_NM", "") or address,
        address=address,
        land_type=normalize_land_type(category),
        price_manwon=to_manwon(it.get("MIN_BID_PRC"), "won"),
        appraisal_manwon=to_manwon(it.get("APSL_ASES_AVG_AMT"), "won"),
        area_m2=parse_area(it.get("GOODS_NM", "")),
        url=DETAIL + urlencode(q),
        deadline=fmt_dtm(it.get("PBCT_CLS_DTM", "")),
        status=it.get("PBCT_CLTR_STAT_NM", ""),
        failed_bids=int(to_float(it.get("USCBD_CNT")) or 0),
        extra={"용도": category, "물건관리번호": it.get("CLTR_MNMT_NO", ""),
               "처분방식": it.get("DPSL_MTD_NM", ""), "상세": it.get("GOODS_NM", ""),
               "최저입찰가율": it.get("FEE_RATE", "")},
    )


def collect(c: Criteria, client: Client, env: dict) -> SourceResult:
    res = SourceResult("onbid")
    key = env.get("DATA_GO_KR_KEY")
    if not key:
        res.ok, res.message = False, "DATA_GO_KR_KEY가 없어 건너뜀"
        return res
    sigungu = c.sigungu_list() if c.sigungu else None
    raw: dict[str, dict] = {}
    # 온비드는 옛 시도명('강원도')을 쓰는 경우가 있어 결과가 없으면 별칭으로 다시 시도한다.
    for sido in sido_variants(c.sido)[:2]:
        for page in range(1, MAX_PAGES + 1):
            params = {"serviceKey": key, "numOfRows": PAGE_SIZE, "pageNo": page,
                      "DPSL_MTD_CD": "0001", "SIDO": sido}
            try:
                items, header = xml_items(client.get(URL, params=params).text)
            except Exception as e:
                res.ok, res.message = False, f"온비드 조회 실패: {e}"
                log.warning(res.message)
                break
            for it in items:
                raw[f"{it.get('CLTR_NO')}-{it.get('PBCT_NO')}"] = it
            total = int(header.get("totalCount") or 0)
            if len(items) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
        if raw:
            break
    res.fetched = len(raw)
    for it in raw.values():
        if "부동산" not in it.get("CTGR_FULL_NM", "") and not any(
                k in it.get("CTGR_FULL_NM", "") for k in ("토지", "주거")):
            continue
        li = to_listing(it)
        if not address_matches(li.address, c.sido, sigungu):
            continue
        li.sido = c.sido
        res.listings.append(li)
    if res.ok:
        res.message = f"공매 부동산 {len(res.listings)}건 (전체 {res.fetched}건 중 지역 일치)"
    return res
