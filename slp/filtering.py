"""수집 결과에 공통 조건(토지 유형·면적·금액)을 적용한다.

면적/금액을 알 수 없는 물건은 버리지 않고 '확인 필요'로 표시한다 (좋은 물건을 놓치지 않도록).
"""
from __future__ import annotations

from .criteria import Criteria
from .models import GENERIC_LAND, LAND_GROUP, Listing


def type_ok(li: Listing, wanted: list[str]) -> bool:
    if not wanted:
        return True
    if li.land_type in wanted:
        return True
    return li.land_type == GENERIC_LAND and any(t in LAND_GROUP for t in wanted)


def apply(c: Criteria, listings: list[Listing]) -> list[Listing]:
    out = []
    for li in listings:
        if not type_ok(li, c.land_types):
            continue
        notes = []
        if li.area_m2 is None:
            if c.area_min_m2 or c.area_max_m2:
                notes.append("면적 미확인")
        else:
            if c.area_min_m2 and li.area_m2 < c.area_min_m2:
                continue
            if c.area_max_m2 and li.area_m2 > c.area_max_m2:
                continue
        if li.price_manwon is None:
            if c.price_min or c.price_max:
                notes.append("금액 미확인")
        else:
            if c.price_min and li.price_manwon < c.price_min:
                continue
            if c.price_max and li.price_manwon > c.price_max:
                continue
        if notes:
            li.extra["확인 필요"] = ", ".join(notes)
        out.append(li)
    return out
