"""국토교통부 실거래가 (공공데이터포털) — 토지·단독/다가구 매매. 참고 시세용.

필요: 환경변수 DATA_GO_KR_KEY (공공데이터포털 일반 인증키, Decoding 값)
활용신청: '국토교통부_토지 매매 실거래가 자료', '국토교통부_단독/다가구 매매 실거래가 자료'
"""
from __future__ import annotations

import datetime as dt
import logging

from ..http import Client, xml_items
from ..models import Trade, normalize_land_type, to_float, to_manwon
from ..regions import Sigungu

log = logging.getLogger("slp")

LAND_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade"
HOUSE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade"


def recent_months(n: int, today: dt.date | None = None) -> list[str]:
    today = today or dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def parse_land(items: list[dict], gu: Sigungu) -> list[Trade]:
    out = []
    for it in items:
        if it.get("cdealType"):  # 해제된 거래 제외
            continue
        out.append(Trade(
            sigungu_code=gu.code,
            sigungu=it.get("sggNm") or gu.name,
            dong=it.get("umdNm", ""),
            jibun=it.get("jibun", ""),
            land_type=normalize_land_type(it.get("jimok")),
            price_manwon=to_manwon(it.get("dealAmount")),
            area_m2=to_float(it.get("dealArea")),
            deal_date=f"{it.get('dealYear', '')}-{int(it.get('dealMonth') or 0):02d}-{int(it.get('dealDay') or 0):02d}",
            kind="land",
            extra={"용도지역": it.get("landUse", ""), "지분거래": it.get("shareDealingType", "")},
        ))
    return out


def parse_house(items: list[dict], gu: Sigungu) -> list[Trade]:
    out = []
    for it in items:
        if it.get("cdealType"):
            continue
        out.append(Trade(
            sigungu_code=gu.code,
            sigungu=it.get("sggNm") or gu.name,
            dong=it.get("umdNm", ""),
            jibun=it.get("jibun", ""),
            land_type="단독주택",
            price_manwon=to_manwon(it.get("dealAmount")),
            area_m2=to_float(it.get("plottageAr")),  # 대지면적 기준으로 비교
            deal_date=f"{it.get('dealYear', '')}-{int(it.get('dealMonth') or 0):02d}-{int(it.get('dealDay') or 0):02d}",
            kind="house",
            extra={"주택유형": it.get("houseType", ""), "연면적": it.get("totalFloorAr", ""),
                   "건축년도": it.get("buildYear", "")},
        ))
    return out


def fetch(client: Client, key: str, sigungu: list[Sigungu], months: int,
          want_land: bool = True, want_house: bool = True) -> tuple[list[Trade], list[str]]:
    trades: list[Trade] = []
    errors: list[str] = []
    jobs = []
    if want_land:
        jobs.append((LAND_URL, parse_land))
    if want_house:
        jobs.append((HOUSE_URL, parse_house))
    for gu in sigungu:
        for ym in recent_months(months):
            for url, parser in jobs:
                try:
                    r = client.get(url, params={"serviceKey": key, "LAWD_CD": gu.code, "DEAL_YMD": ym,
                                                "numOfRows": 1000, "pageNo": 1})
                    items, _ = xml_items(r.text)
                    trades += parser(items, gu)
                except Exception as e:  # 한 달치 실패는 전체를 멈추지 않는다
                    msg = f"{gu.full_name} {ym}: {e}"
                    log.warning("실거래가 조회 실패 %s", msg)
                    errors.append(msg)
                    if "SERVICE_KEY" in str(e) or "인증" in str(e):
                        return trades, errors  # 키 문제면 더 시도할 필요가 없다
    return trades, errors
