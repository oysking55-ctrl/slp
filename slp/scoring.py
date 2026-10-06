"""은퇴 정착 생활 편의 점수 (0~100) — 카카오 로컬 API로 가까운 시설까지의 거리를 잰다.

필요: 환경변수 KAKAO_REST_KEY (developers.kakao.com 앱의 REST API 키, 무료)
가중치·거리 기준은 config/scoring.json 에서 바꿀 수 있다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .http import Client
from .models import Listing

log = logging.getLogger("slp")

API = "https://dapi.kakao.com/v2/local"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "scoring.json"
SEARCH_RADIUS = 20000  # 카카오 최대 반경 (m)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def points(distance_m: float | None, near_km: float, far_km: float) -> float:
    """near 이내면 1, far 이상(또는 못 찾음)이면 0, 사이는 직선으로."""
    if distance_m is None:
        return 0.0
    km = distance_m / 1000
    if km <= near_km:
        return 1.0
    if km >= far_km:
        return 0.0
    return (far_km - km) / (far_km - near_km)


def total_score(distances: dict[str, float | None], factors: list[dict]) -> float:
    weight = sum(f["weight"] for f in factors)
    got = sum(f["weight"] * points(distances.get(f["id"]), f["near_km"], f["far_km"]) for f in factors)
    return round(100 * got / weight, 1) if weight else 0.0


class Kakao:
    def __init__(self, key: str, client: Client):
        self.client = client
        self.headers = {"Authorization": f"KakaoAK {key}"}
        self._geo: dict[str, tuple[float, float] | None] = {}
        self._near: dict[tuple, float | None] = {}

    def geocode(self, address: str) -> tuple[float, float] | None:
        if address in self._geo:
            return self._geo[address]
        pos = None
        for path, q in [("search/address.json", address), ("search/keyword.json", address)]:
            try:
                docs = self.client.get(f"{API}/{path}", params={"query": q}, headers=self.headers).json()["documents"]
            except Exception as e:
                log.warning("카카오 주소 검색 실패 %s: %s", address, e)
                break
            if docs:
                pos = (float(docs[0]["y"]), float(docs[0]["x"]))
                break
        self._geo[address] = pos
        return pos

    def nearest(self, lat: float, lng: float, factor: dict) -> float | None:
        key = (round(lat, 3), round(lng, 3), factor["id"])  # 약 100m 단위로 재사용
        if key in self._near:
            return self._near[key]
        params = {"x": lng, "y": lat, "radius": SEARCH_RADIUS, "sort": "distance", "size": 1}
        best = None
        queries = []
        if factor.get("category"):
            queries.append(("search/category.json", {"category_group_code": factor["category"]}))
        for kw in factor.get("keywords", []):
            queries.append(("search/keyword.json", {"query": kw}))
        for path, extra in queries:
            try:
                docs = self.client.get(f"{API}/{path}", params={**params, **extra},
                                       headers=self.headers).json()["documents"]
            except Exception as e:
                log.warning("카카오 주변 검색 실패: %s", e)
                continue
            if docs and docs[0].get("distance"):
                d = float(docs[0]["distance"])
                best = d if best is None else min(best, d)
        self._near[key] = best
        return best


def score_all(listings: list[Listing], key: str | None, client: Client, limit: int = 300) -> str:
    if not key:
        return "KAKAO_REST_KEY가 없어 생활 편의 점수를 건너뜀"
    cfg = load_config()
    factors = cfg["factors"]
    kakao = Kakao(key, client)
    scored = 0
    for li in listings[:limit]:
        if li.lat is None or li.lng is None:
            pos = kakao.geocode(li.address) if li.address else None
            if not pos:
                continue
            li.lat, li.lng = pos
        dists = {f["id"]: kakao.nearest(li.lat, li.lng, f) for f in factors}
        li.score = total_score(dists, factors)
        li.score_detail = {f["label"]: (round(dists[f["id"]] / 1000, 1) if dists[f["id"]] is not None else None)
                           for f in factors}
        scored += 1
    more = f" (상위 {limit}건만)" if len(listings) > limit else ""
    return f"생활 편의 점수 {scored}건 계산{more}"
