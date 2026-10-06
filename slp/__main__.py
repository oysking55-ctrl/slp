"""명령행: python -m slp search --issue-body body.md [--issue 12] [--summary out.md]
          python -m slp search --criteria criteria.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import search
from .criteria import Criteria, parse_issue_body


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="slp")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="검색 실행")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--issue-body", type=Path, help="GitHub Issue 양식 본문 파일")
    g.add_argument("--criteria", type=Path, help="조건 JSON 파일")
    s.add_argument("--issue", type=int)
    s.add_argument("--summary", type=Path, help="Issue 댓글용 요약을 쓸 파일")
    s.add_argument("--pages-url", default=os.environ.get("PAGES_URL", ""))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        if args.issue_body:
            c = parse_issue_body(args.issue_body.read_text(encoding="utf-8"))
        else:
            c = Criteria.from_dict(json.loads(args.criteria.read_text(encoding="utf-8")))
    except ValueError as e:
        msg = f"### ⚠️ 검색 조건을 확인해 주세요\n\n{e}\n\n이슈 본문을 수정(Edit)하면 다시 검색합니다."
        if args.summary:
            args.summary.write_text(msg, encoding="utf-8")
        print(msg, file=sys.stderr)
        return 2

    result = search.run(c, dict(os.environ), issue=args.issue)
    md = search.summary_markdown(result, args.pages_url)
    if args.summary:
        args.summary.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
