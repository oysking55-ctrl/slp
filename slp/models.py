"""수집 결과의 공통 형식."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PYEONG_M2 = 3.305785

# 화면과 검색 조건에서 쓰는 토지 유형. 출처마다 다른 지목/용도명을 여기로 모은다.
LAND_TYPES = ["대지", "전", "답", "과수원", "임야", "잡종지", "단독주택", "전원주택", "농가주택"]
LAND_GROUP = {"대지", "전", "답", "과수원", "임야", "잡종지"}
GENERIC_LAND = "토지(지목미상)"  # 네이버 '토지'처럼 지목을 알 수 없는 경우
OTHER = "기타"


def normalize_land_type(text: str | None) -> str:
    """'토지 / 대지', '대', '단독', '전원주택' 같은 표기를 LAND_TYPES 중 하나로 바꾼다."""
    if not text:
        return OTHER
    t = text.replace(" ", "")
    for key, val in [
        ("전원주택", "전원주택"),
        ("농가주택", "농가주택"),
        ("단독", "단독주택"),
        ("다가구", "단독주택"),
        ("과수원", "과수원"),
        ("임야", "임야"),
        ("잡종지", "잡종지"),
        ("대지", "대지"),
    ]:
        if key in t:
            return val
    last = t.split("/")[-1]
    if last in ("대", "대지"):
        return "대지"
    if last in ("전", "답"):
        return last
    if last in ("토지",) or t in ("토지",):
        return GENERIC_LAND
    return OTHER


def to_manwon(value: Any, unit: str = "manwon") -> int | None:
    """'12,000'(만원) 또는 원 단위 숫자를 만원 정수로."""
    if value is None or value == "":
        return None
    try:
        n = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    if unit == "won":
        n /= 10000
    return int(round(n))


def to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


@dataclass
class Listing:
    """매물(경매·공매·일반 매매) 한 건."""

    source: str  # onbid | court | naver
    source_id: str
    title: str
    address: str
    land_type: str
    price_manwon: int | None  # 판매가/최저입찰가 (만원)
    area_m2: float | None
    url: str = ""
    sido: str = ""
    sigungu: str = ""
    appraisal_manwon: int | None = None  # 감정가 (경매/공매)
    deadline: str = ""  # 입찰 마감/매각기일
    status: str = ""
    failed_bids: int | None = None
    lat: float | None = None
    lng: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # 평가 단계에서 채움
    score: float | None = None
    score_detail: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def area_pyeong(self) -> float | None:
        return round(self.area_m2 / PYEONG_M2, 1) if self.area_m2 else None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        d["area_pyeong"] = self.area_pyeong
        return d


@dataclass
class Trade:
    """국토부 실거래 한 건 (참고 시세)."""

    sigungu_code: str
    sigungu: str
    dong: str
    jibun: str
    land_type: str
    price_manwon: int | None
    area_m2: float | None
    deal_date: str
    kind: str  # land | house
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def price_per_m2(self) -> float | None:
        if self.price_manwon and self.area_m2:
            return self.price_manwon / self.area_m2
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["price_per_m2"] = round(self.price_per_m2, 2) if self.price_per_m2 else None
        return d
