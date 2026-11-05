import json
import re
from src.state import DebateState
from src.llm import call_gemini
from src.evidence import render_cards
from src.issues import ISSUES
from src.utils import DebateLogger

JUDGE_PROMPT = """당신은 독립적이고 객관적인 최종 '판정자 (Judge)'입니다.
토론자는 'A', 'B'로만 표기됩니다. 어느 쪽이 찬성·반대인지, 어느 쪽 주장이 더 마음에 드는지를 고려하지 말고
논거의 충실성(증거 카드 정합성)과 단서(caveat) 인정 여부만으로 평가하십시오.

반드시 아래 마크다운 목차 규격을 한 항목도 누락하지 말고 끝까지 완결하여 작성하십시오.
글이 중간에 끊기지 않도록 각 항목을 명확하고 완성된 문장으로 서술하십시오.

---
## 1. 쟁점별 평가 매트릭스

### Q1. 생산성 및 노동 강도
1. [합의 완료 (Consensus)]: 양측이 공통으로 인정한 실증적 사실 (카드 ID 병기)
2. [증거 부족 (Insufficient Evidence)]: 양측 모두 입증하지 못했거나 카드 단서상 결론 내릴 수 없는 영역
3. [가치관·해석 차이 (Value Divergence)]: 동일한 증거를 두고 상충하는 해석

### Q2. 향후 10년 한국 고용 총량
1. [합의 완료 (Consensus)]
2. [증거 부족 (Insufficient Evidence)]
3. [가치관·해석 차이 (Value Divergence)]

### Q3. 청년·주니어 고용 타격
1. [합의 완료 (Consensus)]
2. [증거 부족 (Insufficient Evidence)]
3. [가치관·해석 차이 (Value Divergence)]

## 2. 종합 정책적 시사점 및 사회안전망 제언 (필수 작성)
- 증거 카드(예: M2 IMF의 사회안전망 제언, M3 자동화형 vs 증강형, P5 과업 보완 등)에 근거한 구체적 정책 제언을 최소 3개 이상 작성하십시오.
- 각 정책 제언마다 반드시 근거가 된 증거 카드 ID를 명기하십시오. 카드에 없는 기관이나 제언을 지어내지 마십시오.
---

작성 규칙:
- 수치는 [증거 카드]에 있는 값만 쓰고 카드 ID를 병기하십시오. 검증 실패로 표시된 발언의 수치는 근거로 쓰지 마십시오.
- [사회자 정리(ledger)]는 참고 자료입니다. 카드와 모순되면 카드를 따르십시오.
- 어느 한쪽의 일방적 승패를 선언하지 마십시오.
- 반드시 마지막 '2. 종합 정책적 시사점 및 사회안전망 제언' 섹션까지 완성된 형태로 작성하십시오.
"""

_SIDE_LABEL = {"optimus": "A", "criticus": "B"}


def _blind(text: str) -> str:
    """토론자 이름·입장 표지를 제거해 A/B로 치환한다."""
    text = re.sub(r"Optimus(님)?", "A", text, flags=re.I)
    text = re.sub(r"Criticus(님)?", "B", text, flags=re.I)
    return text


def build_blind_transcript(state: DebateState) -> str:
    parts = []
    for c in state["claims"]:
        if c["speaker"] not in _SIDE_LABEL:
            continue
        tag = f"[토론자 {_SIDE_LABEL[c['speaker']]} | {c['issue'] or '입론'} R{c['round_in_issue']}]"
        if c["check"] != "ok":
            tag += f" ⚠️검증실패({'; '.join(c['check_notes'])})"
        conc = f"\n(양보: {_blind(c['concession_reason'])})" if c["concession"] else ""
        parts.append(f"{tag}\n{_blind(c['text'])}{conc}")
    return "\n\n".join(parts)


def build_appendix(state: DebateState) -> str:
    """리포트 부록: 검증 통계와 쟁점별 진행 요약 (코드로 계산, LLM 비의존)"""
    deb = [c for c in state["claims"] if c["speaker"] in _SIDE_LABEL]
    ok = sum(c["check"] == "ok" for c in deb)
    lines = ["", "---", "## 부록: 토의 진행·검증 요약",
             f"- 토론자 발언 {len(deb)}건 중 인용·수치 검증 통과 {ok}건, 미통과 {len(deb) - ok}건",
             f"- 정정 요청이 사용된 발언: {len(state['fixed_ids'])}건"]
    for e in state["ledger"]:
        lines.append(f"- {e['issue']}: {e['rounds']}라운드 진행, 종료 사유: {e['stop_reason']}, 양보 {len(e['concessions'])}건")
    for c in deb:
        if c["check"] != "ok":
            lines.append(f"  - ⚠️ {c['id']} 미통과: {'; '.join(c['check_notes'])}")
    return "\n".join(lines)


def judge_synthesize(state: DebateState) -> dict:
    """최종 판정 및 결론 매트릭스 리포트 생성 노드 (파일 저장은 main에서 한다)"""
    DebateLogger.info("[판정자 Judge]: 전체 토의 내역 블라인드 분석 및 종합 결론 매트릭스 도출 중...")
    cited = sorted({i for c in state["claims"] if c["speaker"] in _SIDE_LABEL
                    for i in c["evidence_ids"] if i in state["evidence_pool"]})
    issue_defs = "\n".join(f"- {k}. {ISSUES[k]['title']}: {ISSUES[k]['question']}" for k in state["issues"])
    ledger = json.dumps(state["ledger"], ensure_ascii=False, indent=1)
    user_prompt = f"""
    토의 대명제: {state['resolution']}
    세부 쟁점 (리포트의 쟁점 제목은 아래를 그대로 사용):
    {issue_defs}

    [증거 카드 — 토론에서 인용된 것]
    {render_cards(state['evidence_pool'], cited)}

    [정책 제언 근거로 쓸 수 있는 공용 카드]
    {render_cards(state['evidence_pool'], [i for i in ('M2', 'M3') if i not in cited])}

    [사회자 정리(ledger)]
    {ledger}

    [토론 전문 (토론자 A/B)]
    {build_blind_transcript(state)}

    위 자료만 근거로 최종 종합 리포트(마크다운)를 작성하십시오.
    """
    report = call_gemini(JUDGE_PROMPT, user_prompt, temperature=0.2) + "\n" + build_appendix(state)
    DebateLogger.section("🏆 [최종 토의 종합 평가 리포트 - Judge]")
    print(report)
    DebateLogger.section("🏆 리포트 도출 완료")
    return {"final_report": report, "stop_reason": "completed"}
