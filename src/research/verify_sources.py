"""2단계: 후보 중 필요한 것만 골라 ego-browser로 원문을 확인한다.

산출물: data/evidence_sources.json (원문 발췌 포함)
실행: uv run python -m src.research.verify_sources [--ids P1,C3] [--candidates] [--pick "검색어앞부분=N"]
  기본: 기존 evidence_pool.json 카드의 URL을 열어 quote 후보를 수집
  --candidates: data/evidence_candidates.json 후보 대상. url이 있으면 원문 발췌, 없으면 검색 결과 링크 수집
"""
import os
import sys
import json
import subprocess
import time

MJS = os.path.abspath(os.path.join(os.path.dirname(__file__), "ego_fetch.mjs"))


def build_targets(use_candidates: bool, ids: list[str] | None) -> list[dict]:
    if use_candidates:
        with open("data/evidence_candidates.json", encoding="utf-8") as f:
            cands = json.load(f)
        return [
            {"id": (c.get('search_query') or c.get('title') or c.get('authors', ''))[:50],
             "url": c.get("url", ""), "query": c.get("search_query", "")}
            for c in cands if c.get("url", "").startswith("http") or c.get("search_query")
        ]
    with open("data/evidence_pool.json", encoding="utf-8") as f:
        pool = json.load(f)
    return [
        {"id": k, "url": v["url"]}
        for k, v in pool.items()
        if v["url"].startswith("http") and (not ids or k in ids)
    ]


def main() -> None:
    args = sys.argv[1:]
    ids = None
    if "--ids" in args:
        ids = args[args.index("--ids") + 1].split(",")
    if "--pick" in args:
        # 검색 결과(evidence_sources.json)에서 사람이 고른 링크만 열어 원문을 발췌한다. 형식: --pick "검색어 앞부분=링크번호(1~5)"
        key, num = args[args.index("--pick") + 1].rsplit("=", 1)
        with open("data/evidence_sources.json", encoding="utf-8") as f:
            prev = json.load(f)
        hit = next(r for r in prev if r["id"].startswith(key) and r.get("links"))
        link = hit["links"][int(num) - 1]
        targets = [{"id": hit["id"], "url": link["url"], "picked_title": link["title"]}]
        keep_prev = prev
    else:
        targets, keep_prev = build_targets("--candidates" in args, ids), None
    os.makedirs("data", exist_ok=True)
    in_path = os.path.abspath("data/_ego_in.json")
    out_path = os.path.abspath("data/evidence_sources.json")
    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False)

    # PowerShell/인용부호 문제를 피하기 위해 한글 없는 한 줄 진입점만 -e로 전달한다.
    fwd = lambda p: p.replace(chr(92), "/")
    entry = (f"globalThis.EGO_IN='{fwd(in_path)}';globalThis.EGO_OUT='{fwd(out_path)}';"
             f"await import('file:///{fwd(MJS)}')")
    started = time.time()
    proc = subprocess.run(
        ["ego-browser", "nodejs", "-e", entry],
        capture_output=True, text=True, encoding="utf-8", timeout=900,
    )
    print(proc.stdout.strip())
    # finish 단계 SDK 오류로 종료 코드가 1이어도, 이번 실행에서 결과 파일이 새로 만들어졌으면 성공으로 본다.
    fresh = os.path.exists(out_path) and os.path.getmtime(out_path) >= started
    if proc.returncode != 0 and not fresh:
        print(proc.stderr.strip())
        raise SystemExit(proc.returncode)
    if keep_prev is not None:  # 선택 결과를 기존 검색 결과에 합쳐 둔다
        with open(out_path, encoding="utf-8") as f:
            fetched = json.load(f)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(keep_prev + fetched, f, ensure_ascii=False, indent=2)
    os.remove(in_path)
    print(f"💾 {out_path}")


if __name__ == "__main__":
    main()
