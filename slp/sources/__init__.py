"""매물 출처별 수집기. 각 모듈은 collect(criteria, client, env) -> SourceResult 를 제공한다."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Listing


@dataclass
class SourceResult:
    source: str
    listings: list[Listing] = field(default_factory=list)
    ok: bool = True
    message: str = ""
    fetched: int = 0  # 필터 전 건수

    def summary(self) -> dict[str, Any]:
        return {"source": self.source, "ok": self.ok, "message": self.message,
                "fetched": self.fetched, "count": len(self.listings)}


def get_collector(name: str):
    from . import court, naver, onbid

    return {"onbid": onbid.collect, "court": court.collect, "naver": naver.collect}[name]
