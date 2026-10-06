"""법정동코드 원본(JSON)에서 config/regions.json(시도·시군구 목록)을 만든다.

원본: PublicDataReader 패키지에 포함된 raw/code_bdong.json (행정안전부 법정동코드 전체자료).
    pip download --no-deps PublicDataReader && unzip ... 후
    python scripts/build_regions.py path/to/code_bdong.json
"""
import json
import sys
from pathlib import Path


# 원본 자료 이후의 행정구역 개편 반영 (실거래가 API는 현행 코드를 사용한다).
RENAMED_SIDO = {  # 옛 시도코드: (새 시도코드, 새 이름)
    "42": ("51", "강원특별자치도"),  # 2023-06
    "45": ("52", "전북특별자치도"),  # 2024-01
}
EXTRA_SIGUNGU = {
    "36": [("36110", "세종특별자치시")],
    "41": [("41192", "부천시 원미구"), ("41194", "부천시 소사구"), ("41196", "부천시 오정구")],  # 2024-01 구 재설치
}
MOVED_SIGUNGU = {"47720": ("27", "27720")}  # 군위군: 경북 -> 대구 (2023-07)


def apply_fixes(sidos: dict) -> None:
    for old, (new, name) in RENAMED_SIDO.items():
        if old in sidos:
            s = sidos.pop(old)
            s["code"], s["name"] = new, name
            for g in s["sigungu"]:
                g["code"] = new + g["code"][2:]
            sidos[new] = s
    for code, (sd, new_code) in MOVED_SIGUNGU.items():
        for s in sidos.values():
            for g in list(s["sigungu"]):
                if g["code"] == code:
                    s["sigungu"].remove(g)
                    sidos[sd]["sigungu"].append({"code": new_code, "name": g["name"]})
    for sd, extras in EXTRA_SIGUNGU.items():
        have = {g["code"] for g in sidos[sd]["sigungu"]}
        sidos[sd]["sigungu"] += [{"code": c, "name": n} for c, n in extras if c not in have]
    for s in sidos.values():  # 출장소는 별도 행정구역이 아니다
        s["sigungu"] = [g for g in s["sigungu"] if "출장" not in g["name"]]


def main(src: str) -> None:
    raw = json.loads(Path(src).read_text(encoding="utf-8"))
    rows = [{k: raw[k][i] for k in raw} for i in raw["시도코드"]]
    sidos: dict[str, dict] = {}
    for r in rows:
        if r["말소일자"] is not None and r["말소일자"] == r["말소일자"]:  # NaN != NaN
            continue
        code = str(r["법정동코드"])
        if not code.endswith("00000"):
            continue
        sd = str(r["시도코드"])
        if code.endswith("00000000"):
            sidos.setdefault(sd, {"code": sd, "name": r["시도명"], "sigungu": []})
            continue
        name = r["시군구명"]
        if not isinstance(name, str):
            continue
        sidos.setdefault(sd, {"code": sd, "name": r["시도명"], "sigungu": []})
        sidos[sd]["sigungu"].append({"code": code[:5], "name": name})
    apply_fixes(sidos)
    out = sorted(sidos.values(), key=lambda s: s["code"])
    for s in out:
        s["sigungu"].sort(key=lambda g: g["code"])
    dest = Path(__file__).resolve().parent.parent / "config" / "regions.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{dest}: 시도 {len(out)}개, 시군구 {sum(len(s['sigungu']) for s in out)}개")


if __name__ == "__main__":
    main(sys.argv[1])
