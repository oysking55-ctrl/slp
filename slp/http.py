"""HTTP 공통: 재시도, 요청 간격, 브라우저와 비슷한 헤더."""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("slp")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class Client:
    def __init__(self, min_interval: float = 0.3, timeout: float = 20.0):
        self.s = requests.Session()
        retry = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "POST"])
        self.s.mount("http://", HTTPAdapter(max_retries=retry))
        self.s.mount("https://", HTTPAdapter(max_retries=retry))
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def _wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()

    def get(self, url: str, **kw: Any) -> requests.Response:
        self._wait()
        kw.setdefault("timeout", self.timeout)
        r = self.s.get(url, **kw)
        r.raise_for_status()
        return r

    def post(self, url: str, **kw: Any) -> requests.Response:
        self._wait()
        kw.setdefault("timeout", self.timeout)
        r = self.s.post(url, **kw)
        r.raise_for_status()
        return r


def xml_items(text: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    """공공데이터포털 형식 XML -> (item 목록, header).

    오류 응답(OpenAPI_ServiceResponse)이면 ValueError.
    """
    root = ET.fromstring(text)
    if root.tag == "OpenAPI_ServiceResponse":
        msg = root.findtext(".//errMsg") or ""
        reason = root.findtext(".//returnAuthMsg") or root.findtext(".//returnReasonCode") or ""
        raise ValueError(f"API 오류: {msg} {reason}".strip())
    h = root.find("header")
    header = {c.tag: (c.text or "").strip() for c in h} if h is not None else {}
    code = header.get("resultCode", "")
    if code and code not in ("00", "000"):
        raise ValueError(f"API 오류 {code}: {header.get('resultMsg', '')}")
    items = []
    for it in root.iter("item"):
        items.append({c.tag: (c.text or "").strip() for c in it})
    total = root.findtext(".//totalCount")
    if total is not None:
        header["totalCount"] = total.strip()
    return items, header
