"""검색 조건: GitHub Issue 양식 본문 또는 JSON에서 읽는다."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from . import regions
from .models import LAND_TYPES

SOURCES = {
    "onbid": "온비드 공매",
    "court": "법원경매",
    "naver": "네이버 부동산",
}
DEFAULT_SOURCES = ["onbid", "court"]

# Issue 양식(.github/ISSUE_TEMPLATE/search.yml)의 label -> 필드
FORM_LABELS = {
    "검색 이름": "name",
    "시도": "sido",
    "시군구": "sigungu",
    "토지 유형": "land_types",
    "최소 면적": "area_min",
    "최대 면적": "area_max",
    "면적 단위": "area_unit",
    "최소 금액": "price_min",
    "최대 금액": "price_max",
    "검색 출처": "sources",
    "실거래가 비교 기간": "market_months",
    "메모": "memo",
}
NO_RESPONSE = {"", "_No response_", "None"}


@dataclass
class Criteria:
    sido: str
    sigungu: list[str] = field(default_factory=list)
    land_types: list[str] = field(default_factory=list)  # 비어 있으면 전체
    area_min_m2: float | None = None
    area_max_m2: float | None = None
    price_min: int | None = None  # 만원
    price_max: int | None = None  # 만원
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    market_months: int = 6
    name: str = ""
    memo: str = ""

    def __post_init__(self) -> None:
        s = regions.find_sido(self.sido)
        if not s:
            raise ValueError(f"알 수 없는 시도: {self.sido}")
        self.sido = s["name"]
        bad = [t for t in self.land_types if t not in LAND_TYPES]
        if bad:
            raise ValueError(f"알 수 없는 토지 유형: {bad}")
        bad = [x for x in self.sources if x not in SOURCES]
        if bad:
            raise ValueError(f"알 수 없는 출처: {bad}")
        if self.price_min and self.price_max and self.price_min > self.price_max:
            raise ValueError("최소 금액이 최대 금액보다 큽니다")
        if self.area_min_m2 and self.area_max_m2 and self.area_min_m2 > self.area_max_m2:
            raise ValueError("최소 면적이 최대 면적보다 큽니다")
        self.market_months = max(0, min(int(self.market_months), 24))

    def sigungu_list(self) -> list[regions.Sigungu]:
        return regions.resolve(self.sido, self.sigungu)

    def title(self) -> str:
        if self.name:
            return self.name
        where = self.sido + (" " + ",".join(self.sigungu) if self.sigungu else "")
        return f"{where} {'·'.join(self.land_types) or '전체 유형'}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Criteria":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def parse_money(text: str) -> int | None:
    """'3억 5000', '35000', '3.5억', '5천만' -> 만원 정수."""
    t = text.replace(",", "").replace(" ", "").replace("원", "")
    if t in NO_RESPONSE:
        return None
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)억)?(?:(\d+(?:\.\d+)?)(천만|천|만)?)?", t)
    if not m or not (m.group(1) or m.group(2)):
        raise ValueError(f"금액을 이해할 수 없습니다: {text!r} (예: 30000, 3억, 3억5000)")
    total = float(m.group(1) or 0) * 10000
    if m.group(2):
        n = float(m.group(2))
        total += n * {"천만": 1000, "천": 1000, "만": 1, None: 1}[m.group(3)]
    return int(round(total))


def parse_number(text: str) -> float | None:
    t = text.replace(",", "").strip()
    if t in NO_RESPONSE:
        return None
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        raise ValueError(f"숫자를 이해할 수 없습니다: {text!r}")
    return float(m.group())


def _split_list(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,\n/·]", text) if x.strip() and x.strip() not in NO_RESPONSE]


def parse_issue_body(body: str) -> Criteria:
    """GitHub Issue 양식이 만든 마크다운('### 라벨' + 값)을 Criteria로."""
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in body.replace("\r\n", "\n").split("\n"):
        h = re.match(r"^###\s+(.*)$", line)
        if h:
            if current:
                sections[current] = "\n".join(buf).strip()
            label = h.group(1).strip()
            current = next((v for k, v in FORM_LABELS.items() if label.startswith(k)), None)
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()

    def val(key: str) -> str:
        v = sections.get(key, "").strip()
        return "" if v in NO_RESPONSE else v

    def checked(key: str) -> list[str]:
        v = sections.get(key, "")
        boxes = re.findall(r"- \[[xX]\]\s*(.+)", v)
        return [b.strip() for b in boxes] if boxes or "- [" in v else _split_list(val(key))

    if not val("sido"):
        raise ValueError("시도를 선택해 주세요")
    unit = val("area_unit") or "㎡"
    factor = 3.305785 if "평" in unit else 1.0

    def area(key: str) -> float | None:
        n = parse_number(val(key))
        return round(n * factor, 2) if n is not None else None

    land = [t.split("(")[0].strip() for t in checked("land_types")]
    src_labels = checked("sources")
    sources = [k for k, label in SOURCES.items() if any(label in s for s in src_labels)]
    months = val("market_months")
    return Criteria(
        name=val("name"),
        sido=val("sido"),
        sigungu=_split_list(val("sigungu")),
        land_types=land,
        area_min_m2=area("area_min"),
        area_max_m2=area("area_max"),
        price_min=parse_money(val("price_min")) if val("price_min") else None,
        price_max=parse_money(val("price_max")) if val("price_max") else None,
        sources=sources or list(DEFAULT_SOURCES),
        market_months=int(parse_number(months)) if months else 6,
        memo=val("memo"),
    )
