"""시도·시군구 목록(config/regions.json) 조회."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REGIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "regions.json"

# 출처마다 옛 이름을 쓰는 경우가 있어 주소 비교용 별칭을 둔다.
SIDO_ALIASES = {
    "강원특별자치도": ["강원도", "강원"],
    "전북특별자치도": ["전라북도", "전북"],
    "제주특별자치도": ["제주도", "제주"],
    "세종특별자치시": ["세종시", "세종"],
    "서울특별시": ["서울시", "서울"],
    "부산광역시": ["부산시", "부산"],
    "대구광역시": ["대구시", "대구"],
    "인천광역시": ["인천시", "인천"],
    "광주광역시": ["광주시", "광주"],
    "대전광역시": ["대전시", "대전"],
    "울산광역시": ["울산시", "울산"],
    "경기도": ["경기"],
    "충청북도": ["충북"],
    "충청남도": ["충남"],
    "전라남도": ["전남"],
    "경상북도": ["경북"],
    "경상남도": ["경남"],
}


@dataclass(frozen=True)
class Sigungu:
    code: str  # 5자리 (실거래가 LAWD_CD)
    name: str  # 예: '홍천군', '수원시 장안구'
    sido_code: str
    sido_name: str

    @property
    def cortar_no(self) -> str:
        return self.code + "00000"

    @property
    def full_name(self) -> str:
        return f"{self.sido_name} {self.name}"


@lru_cache
def load() -> list[dict]:
    return json.loads(REGIONS_PATH.read_text(encoding="utf-8"))


def sido_names() -> list[str]:
    return [s["name"] for s in load()]


def find_sido(name: str) -> dict | None:
    name = name.strip()
    for s in load():
        if name == s["name"] or name in SIDO_ALIASES.get(s["name"], []):
            return s
    return None


def sido_variants(name: str) -> list[str]:
    return [name, *SIDO_ALIASES.get(name, [])]


def resolve(sido: str, sigungu_names: list[str] | None = None) -> list[Sigungu]:
    """시도와 (선택) 시군구 이름으로 실거래가 조회용 시군구 목록을 만든다.

    '수원시'처럼 구가 있는 시를 고르면 하위 구('수원시 장안구' 등)로 펼친다.
    시군구를 지정하지 않으면 시도 전체.
    """
    s = find_sido(sido)
    if not s:
        raise ValueError(f"알 수 없는 시도: {sido}")
    all_gu = [Sigungu(g["code"], g["name"], s["code"], s["name"]) for g in s["sigungu"]]
    if not sigungu_names:
        wanted = all_gu
    else:
        wanted = []
        for raw in sigungu_names:
            n = raw.strip()
            if not n:
                continue
            hits = [g for g in all_gu if g.name == n or g.name.replace(" ", "") == n.replace(" ", "")]
            if not hits:
                hits = [g for g in all_gu if g.name.startswith(n)]
            if not hits:
                raise ValueError(f"{s['name']}에 '{n}' 시군구가 없습니다")
            wanted += hits
    # 하위 구가 있는 시(예: 수원시)는 구로 대체한다.
    out = []
    for g in wanted:
        children = [c for c in all_gu if c.name.startswith(g.name + " ")]
        out += children or [g]
    seen, uniq = set(), []
    for g in out:
        if g.code not in seen:
            seen.add(g.code)
            uniq.append(g)
    return uniq


def address_matches(address: str, sido: str, sigungu: list[Sigungu] | None) -> bool:
    """주소 문자열이 선택한 지역 안인지 (출처마다 시도 표기가 달라 별칭으로 비교)."""
    a = address.replace(" ", "")
    if not any(v.replace(" ", "") in a for v in sido_variants(sido)):
        return False
    if not sigungu:
        return True
    return any(g.name.replace(" ", "") in a or g.name.split(" ")[0] in a for g in sigungu)
