"""1단계: Gemini Deep Research 에이전트로 쟁점별 후보 문헌을 넓게 탐색한다.

산출물: data/research/deep_research_{Q}.md (원문 보고서), data/evidence_candidates.json (후보 목록)
실행: uv run python -m src.research.deep_research [Q1 Q2 Q3] [--extract-only]
"""
import os
import sys
import json
import time
from google import genai

from src.llm import call_gemini, extract_json

# Deep Research 에이전트는 us-central1을 지원하지 않아 global 리전을 사용한다.
AGENT = os.getenv("DEEP_RESEARCH_AGENT", "deep-research-preview-04-2026")
research_client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id"),
    location="global",
)

ISSUE_QUERIES = {
    "Q1": "생성형 AI가 근로자 생산성과 노동 강도에 미치는 영향을 실증한 1차 연구(RCT, 행정자료, 현장 실험). "
          "NBER, SSRN, 학술지(QJE, Science, Org. Sci. 등)의 논문을 우선하고, 효과 크기와 한계(적용 범위, 표본)를 명시.",
    "Q2": "향후 10년 한국 고용 총량에 대한 AI의 영향을 추정한 연구(KDI, 한국은행, 한국노동연구원, 국회예산정책처, IMF, Acemoglu 등). "
          "순고용 증감 추정치, 가정, 신규 직무 창출 효과 반영 여부를 명시.",
    "Q3": "AI가 청년·주니어 고용에 미친 영향을 분석한 연구(Brynjolfsson 'Canaries', 한국은행 이슈노트, 핀란드 ETLA 등). "
          "AI 외 요인(경기, 재택근무, 인구)과의 구분 여부, 인과 추정 여부를 명시.",
}

CANDIDATE_PROMPT = """아래 리서치 보고서에서 근거로 쓰인 개별 연구/보고서를 모두 추출해 JSON으로만 응답하십시오.
형식: {"candidates": [{"title": "", "authors": "", "year": "", "venue": "", "url": "", "claim": "핵심 주장 한 문장(수치 포함)", "side": "pro|con|both", "search_query": "원문을 찾기 위한 검색어"}]}
규칙:
- 보고서에 실제로 언급된 연구만 추출하고, 보고서에 없는 내용은 지어내지 마십시오.
- title/url을 보고서에서 알 수 없으면 빈 문자열로 두고, 대신 기관명·저자·연도·주제를 담은 search_query를 반드시 채우십시오.
- 한 기관이 여러 연구를 언급했으면 각각 별도 항목으로 추출하십시오.

[보고서]
"""


def run_deep_research(issue: str, poll_sec: int = 20, timeout_sec: int = 1800) -> str:
    interaction = research_client.interactions.create(
        agent=AGENT, input=ISSUE_QUERIES[issue], background=True
    )
    print(f"[{issue}] Deep Research 시작: {interaction.id}")
    start = time.time()
    while True:
        interaction = research_client.interactions.get(interaction.id)
        if interaction.status == "completed":
            return interaction.output_text or ""
        if interaction.status in ("failed", "cancelled", "incomplete", "budget_exceeded"):
            raise RuntimeError(f"[{issue}] Deep Research 실패: {interaction.status} {interaction.errors}")
        if time.time() - start > timeout_sec:
            raise TimeoutError(f"[{issue}] Deep Research 시간 초과")
        print(f"  [{issue}] {interaction.status}... ({int(time.time() - start)}s)")
        time.sleep(poll_sec)


def extract_candidates(issue: str, report: str) -> list[dict]:
    raw = call_gemini("", CANDIDATE_PROMPT + report, temperature=0.0)
    with open(f"data/research/extract_raw_{issue}.txt", "w", encoding="utf-8") as f:
        f.write(raw)  # 파싱 실패 시 원문 확인용
    out = []
    for c in extract_json(raw).get("candidates", []):
        c["issue"] = issue
        out.append(c)
    return out


def dedupe(candidates: list[dict]) -> list[dict]:
    """URL > 제목 > (저자+연도+검색어) 순으로 키를 만들고, 키가 같은 항목만 병합한다. 빈 값끼리는 병합하지 않는다."""
    merged: dict[tuple, dict] = {}
    for c in candidates:
        key = (c.get("url") or c.get("title") or
               f"{c.get('authors', '')}|{c.get('year', '')}|{c.get('search_query', '') or c.get('claim', '')}")
        if key in merged:
            issues = set(merged[key]["issue"].split(",")) | set(c["issue"].split(","))
            merged[key]["issue"] = ",".join(sorted(issues))
        else:
            merged[key] = c
    return list(merged.values())


def main(issues: list[str], extract_only: bool = False) -> None:
    os.makedirs("data/research", exist_ok=True)
    candidates = []
    for q in issues:
        path = f"data/research/deep_research_{q}.md"
        if extract_only:  # 이미 받은 보고서로 후보 추출만 다시 수행 (Deep Research 재실행 방지)
            with open(path, encoding="utf-8") as f:
                report = f.read()
        else:
            report = run_deep_research(q)
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
        found = extract_candidates(q, report)
        print(f"[{q}] 후보 {len(found)}건 추출")
        candidates += found

    result = dedupe(candidates)
    with open("data/evidence_candidates.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    no_url = sum(1 for c in result if not c.get("url"))
    print(f"data/evidence_candidates.json 저장 ({len(result)}건, URL 없음 {no_url}건)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args or list(ISSUE_QUERIES), extract_only="--extract-only" in sys.argv)
