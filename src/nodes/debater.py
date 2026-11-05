from typing import List, Optional
from src.state import DebateState, Claim
from src.llm import call_gemini_json
from src.issues import ISSUES
from src.evidence import render_cards, latest_claim, clip
from src.verification import inline_tags
from src.utils import DebateLogger

PERSONAS = {
    "optimus": {
        "name": "혁신주의자 (Optimus)", "side": "pro", "label": "💡", "opponent": "criticus",
        "stance": "AI는 노동 강도를 완화하고 생산성을 증강(Augmentation)하며 신규 직무를 창출하여 인류를 이롭게 한다.",
        "concede": "청년층 단기 채용 둔화 등 상대 근거가 카드상 타당하면 인정하되, 직무 재교육과 신규 과업 복원 효과(P5)로 극복 가능한지 논하십시오.",
        "open_hint": "AI가 인간의 과업을 증강하여 노동의 질과 생산성을 혁신함을 주장하는 독립 입론",
    },
    "criticus": {
        "name": "비판·신중론자 (Criticus)", "side": "con", "label": "⚠️", "opponent": "optimus",
        "stance": "AI는 신규 일자리 창출보다 대체 효과(Displacement)가 빠르며, 청년층 채용 절벽과 노동소득분배율 하락 등 사회적 부작용을 초래한다.",
        "concede": "상대의 생산성 근거가 카드상 사실이면 인정하되, 그 과실의 분배와 주니어 노동자의 고용 안정성 문제를 지적하십시오.",
        "open_hint": "AI 확산이 양극화와 청년 고용 절벽을 야기할 수 있음을 경고하는 독립 입론",
    },
}

RULES = """토의 규칙 (반드시 지키십시오):
1. 아래 [증거 카드]에 적힌 수치만 사용하십시오. 새로 계산·반올림·추정한 수치, 카드에 없는 연구는 금지입니다.
2. 수치를 쓰는 문장에는 그 수치가 실제로 들어 있는 카드 ID를 괄호로 표기하십시오. 예: "해결 건수가 15% 증가했습니다(P1)." 다른 카드의 수치를 섞어 쓰지 마십시오.
3. 인용한 카드의 불리한 단서(caveat)를 숨기지 말고 최소 1개 이상 솔직히 밝히십시오.
4. 상대 주장은 (a) 표본·과업의 한계 (b) 상관과 인과의 구분 (c) 대안적 설명(경기, 인구, 재택근무 등)을 중심으로 반박하십시오.
5. concession: 상대 주장이 카드 근거로 명백히 타당할 때만 true로 하고, concession_reason에 어느 카드의 어떤 사실을 인정하는지 적으십시오. 아니면 false, 사유는 null입니다. [agreement_level = 0.4] 원칙에 따라 타당한 팩트는 유연하게 수용하되, 무조건적 타협과 억지 버티기를 모두 금지합니다.
6. 이전 자신의 발언을 반복하지 말고 새로운 근거나 새로운 반박을 제시하십시오.
7. 공백 포함 700자 이내로 작성하십시오.
출력은 JSON 하나만:
{"text": "발언 본문", "evidence_ids": ["P1"], "concession": false, "concession_reason": null}"""


def _system(speaker: str) -> str:
    p = PERSONAS[speaker]
    return f"당신은 '{p['name']}'입니다.\n입장: {p['stance']}\n{p['concede']}\n\n{RULES}"


def _own_history(state: DebateState, speaker: str) -> str:
    mine = [c for c in state["claims"] if c["speaker"] == speaker][-2:]
    return "\n".join(f"- {clip(c['text'], 400)}" for c in mine) or "(없음)"


def _build_claim(state: DebateState, speaker: str, issue: Optional[str], r_num: int, data: dict) -> Claim:
    p = PERSONAS[speaker]
    text = str(data["text"]).strip()
    # 모델이 선언한 ID와 본문 괄호 태그를 합쳐 실제 인용 목록으로 사용 (풀에 없는 ID도 남겨 Verifier가 잡게 한다)
    declared = [str(i) for i in data.get("evidence_ids", []) or []]
    ids = list(dict.fromkeys(declared + sorted(inline_tags(text))))
    reason = (data.get("concession_reason") or "").strip() or None
    cid = f"claim_{p['side']}_open" if issue is None else f"claim_{p['side']}_{issue}_{r_num}"
    return {
        "id": cid, "speaker": speaker, "side": p["side"], "issue": issue, "round_in_issue": r_num,
        "text": text, "evidence_ids": ids, "check": "pending", "check_notes": [],
        # 사유 없는 양보는 인정하지 않는다 (형식적 양보 방지)
        # Round 0 입론은 상대 발언을 보지 못하므로 양보가 성립하지 않는다
        "concession": bool(data.get("concession")) and reason is not None and issue is not None,
        "concession_reason": reason if issue is not None else None,
    }


def speak(state: DebateState, speaker: str, issue: Optional[str], r_num: int,
          feedback: Optional[List[str]] = None, previous_text: str = "") -> Claim:
    """Round 0 입론(issue=None) 또는 쟁점 반론을 생성한다. feedback이 있으면 정정 요청이다."""
    p = PERSONAS[speaker]
    pool = state["evidence_pool"]
    if issue is None:
        cards = render_cards(pool, list(pool))
        task = (f"토의 명제: {state['resolution']}\n세부 쟁점: "
                + " / ".join(f"{k}. {v['title']}" for k, v in ISSUES.items())
                + f"\n\n상대의 발언은 볼 수 없습니다. {p['open_hint']}을 작성하십시오.")
        history = ""
    else:
        info = ISSUES[issue]
        cards = render_cards(pool, info["evidence"])
        question = latest_claim(state["claims"], "harmony", issue)
        opp = latest_claim(state["claims"], p["opponent"])
        task = (f"쟁점 {issue} ({info['title']}), Round {r_num}\n쟁점 질문: {info['question']}\n"
                f"사회자 질의:\n{question['text'] if question else '(없음)'}\n\n"
                f"상대({PERSONAS[p['opponent']]['name']})의 가장 최근 발언:\n{opp['text'] if opp else '(없음)'}\n\n"
                "사회자 질의에 답하고 상대 주장에 반박하십시오.")
        history = f"\n[본인의 이전 발언 — 반복 금지]\n{_own_history(state, speaker)}\n"
    prompt = f"[증거 카드]\n{cards}\n\n{task}\n{history}"
    if feedback:
        prompt += ("\n[정정 요청] 직전 발언에서 검증 오류가 발견되었습니다:\n- " + "\n- ".join(feedback)
                   + f"\n\n직전 발언:\n{previous_text}\n\n같은 입장과 논지를 유지하되, 위 수치를 카드에 실제로 있는 값으로 고치거나 "
                     "해당 수치를 삭제하여 다시 작성하십시오.")
    data = call_gemini_json(_system(speaker), prompt, required=["text"])
    return _build_claim(state, speaker, issue, r_num, data)


def _announce(claim: Claim, title: str) -> None:
    p = PERSONAS[claim["speaker"]]
    DebateLogger.speech(
        claim["speaker"], p["name"], title, claim["text"],
        ids=claim["evidence_ids"], concession=claim["concession_reason"]
    )


def optimus_opening(state: DebateState) -> dict:
    """찬성 측 Round 0 독립 입론 (상대 발언 미열람)"""
    DebateLogger.info("[찬성 Optimus]: Round 0 독립 입론 생성 중...")
    claim = speak(state, "optimus", None, 0)
    _announce(claim, "입론")
    return {"openings": {"pro": claim["text"]}, "claims": [claim]}


def criticus_opening(state: DebateState) -> dict:
    """반대 측 Round 0 독립 입론 (상대 발언 미열람)"""
    DebateLogger.info("[반대 Criticus]: Round 0 독립 입론 생성 중...")
    claim = speak(state, "criticus", None, 0)
    _announce(claim, "입론")
    return {"openings": {"con": claim["text"]}, "claims": [claim]}


def optimus_rebuttal(state: DebateState) -> dict:
    """찬성 측 쟁점 반론 노드"""
    issue, r_num = state["issues"][state["issue_idx"]], state["round_in_issue"]
    claim = speak(state, "optimus", issue, r_num)
    _announce(claim, f"반론 - {issue} R{r_num}")
    return {"claims": [claim], "stage": "optimus_rebuttal"}


def criticus_rebuttal(state: DebateState) -> dict:
    """반대 측 쟁점 재반론 노드 (같은 라운드의 Optimus 발언을 본다)"""
    issue, r_num = state["issues"][state["issue_idx"]], state["round_in_issue"]
    claim = speak(state, "criticus", issue, r_num)
    _announce(claim, f"재반론 - {issue} R{r_num}")
    return {"claims": [claim], "stage": "criticus_rebuttal"}


def fix_claims(state: DebateState) -> dict:
    """Verifier가 불일치로 표시한 발언을 1회 정정한다 (기획안: 수치 정정 기회 1회)."""
    done = set(state["fixed_ids"])
    targets = [c for c in state["claims"]
               if c["speaker"] in PERSONAS and c["check"] in ("mismatch", "no_evidence") and c["id"] not in done]
    fixed = []
    for c in targets:
        DebateLogger.fix_request(c["speaker"], c["id"], c["check_notes"])
        new = speak(state, c["speaker"], c["issue"], c["round_in_issue"],
                    feedback=c["check_notes"], previous_text=c["text"])
        _announce(new, "정정본")
        fixed.append(new)
    return {"claims": fixed, "fixed_ids": [c["id"] for c in targets]}
