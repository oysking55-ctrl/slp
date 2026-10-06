"""실거래가와 비교: 같은 시군구·같은 유형의 ㎡당 중위 거래가 대비 몇 % 인지."""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from .models import PYEONG_M2, Listing, Trade

MIN_SAMPLES = 3


def _key_gu(name: str) -> str:
    return name.replace(" ", "")


def summarize(trades: list[Trade]) -> list[dict]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for t in trades:
        if t.price_per_m2:
            groups[(t.sigungu, t.land_type)].append(t.price_per_m2)
    rows = []
    for (gu, lt), vals in sorted(groups.items()):
        m = median(vals)
        rows.append({"sigungu": gu, "land_type": lt, "count": len(vals),
                     "median_per_m2": round(m, 2), "median_per_pyeong": round(m * PYEONG_M2, 1)})
    return rows


def compare(listings: list[Listing], trades: list[Trade]) -> None:
    by_gu_type: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_gu_kind: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_dong: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for t in trades:
        p = t.price_per_m2
        if not p:
            continue
        g = _key_gu(t.sigungu)
        by_gu_type[(g, t.land_type)].append(p)
        by_gu_kind[(g, t.kind)].append(p)
        by_dong[(g, t.dong, t.land_type)].append(p)
    gus = {k[0] for k in by_gu_kind}
    for li in listings:
        if not (li.price_manwon and li.area_m2):
            continue
        addr = li.address.replace(" ", "")
        gu = next((g for g in sorted(gus, key=len, reverse=True) if g in addr), None)
        if not gu:
            continue
        kind = "house" if "주택" in li.land_type else "land"
        dong = next((d for (g, d, lt) in by_dong if g == gu and lt == li.land_type and d and d in li.address), None)
        for label, vals in [
            (f"{dong} {li.land_type}", by_dong.get((gu, dong, li.land_type), []) if dong else []),
            (f"{gu} {li.land_type}", by_gu_type.get((gu, li.land_type), [])),
            (f"{gu} {'단독주택' if kind == 'house' else '토지 전체'}", by_gu_kind.get((gu, kind), [])),
        ]:
            if len(vals) >= MIN_SAMPLES:
                ref = median(vals)
                mine = li.price_manwon / li.area_m2
                li.market = {"basis": label, "samples": len(vals), "median_per_m2": round(ref, 2),
                             "listing_per_m2": round(mine, 2), "ratio": round(mine / ref, 2)}
                break
