from src.state import DebateState, Claim
from src.llm import call_gemini, call_gemini_json
from src.issues import ISSUES, MAX_ROUNDS
from src.evidence import latest_claim, clip
from src.utils import DebateLogger

HARMONY_SYSTEM_PROMPT = """당신은 고도로 훈련된 AI 심층 토의 전문 사회자 '중재자 (Harmony)'입니다.
토의 규칙:
1. 완벽한 중립을 지키며, 특정 입장의 결론을 미리 유도하거나 승패를 선언하지 마십시오.
2. 토론자들이 추상적인 주장을 남발할 경우, 공용 증거 풀의 evidence_id(P1~P10, C1~C7, M1~M3)와 구체적 수치(%)를 엄격히 요구하십시오.
3. 양측의 발언이 평행선을 달리거나 도돌이표가 될 때, "어떻게 활용하는가(자동화형 대체인가 vs 인간 역량 증강형 보완인가? M3)" 프레임을 제시하며 핵심 쟁점을 좁히십시오.
4. 라운드 종료 시 양측의 '합의된 사실(Consensus)', '사실 불일치(Factual Conflict)', '가치관 차이(Value Divergence)'를 명확히 정리하십시오.
"""


def _claim(cid: str, text: str, issue=None, r_num: int = 0) -> Claim:
    return {"id": cid, "speaker": "harmony", "side": None, "issue": issue, "round_in_issue": r_num,
            "text": text, "evidence_ids": [], "check": "ok", "check_notes": [],
            "concession": False, "concession_reason": None}


def harmony_frame(state: DebateState) -> dict:
    """토의 시작 발제 및 규칙 공표 노드"""
    DebateLogger.info("[사회자 Harmony]: 토의 개회 및 3대 쟁점 발제 중...")
    issues = "\n".join(f"{i+1}. {k}: {ISSUES[k]['title']} ({ISSUES[k]['question']})"
                       for i, k in enumerate(state["issues"]))
    user_prompt = f"""
    토의 주제: {state['resolution']}
    다룰 세부 쟁점:
    {issues}

    역할:
    - 찬성 측 (Optimus): 생산성 증강, 노동 강도 완화, 숙련 격차 축소 중심
    - 반대 측 (Criticus): 일자리 대체, 청년 채용 절벽, 거시 이득 과대 추정 비판 중심

    사회자로서 양측 토론자에게 토의의 규칙(모든 주장에 evidence_id 명시, 카드에 있는 수치만 사용, 불리한 단서 caveat 솔직 병기 의무, 근거 있는 양보 허용)을 엄격히 고지하고,
    독립 입론(Round 0) 작성을 요청하는 개회사를 품격 있고 간결하게(400자 이내) 작성하십시오.
    """
    speech = call_gemini(HARMONY_SYSTEM_PROMPT, user_prompt)
    DebateLogger.speech("harmony", "사회자 Harmony", "개회 발제", speech)
    return {"claims": [_claim("claim_h_0", speech)], "stage": "openings"}


def harmony_cross_examine(state: DebateState) -> dict:
    """쟁점별 교차 질문 노드: 쟁점 질문과 양측 최신 발언의 맹점을 짚는다."""
    issue = state["issues"][state["issue_idx"]]
    r_num = state["round_in_issue"]
    info = ISSUES[issue]
    DebateLogger.info(f"[사회자 Harmony]: 쟁점 {issue} (Round {r_num}) 교차 질문 제시 중...")

    pro = latest_claim(state["claims"], "optimus")
    con = latest_claim(state["claims"], "criticus")
    pool = state["evidence_pool"]
    caveats = "\n".join(f"- [{i}] {clip(pool[i]['caveat'], 90)}" for i in info["evidence"])
    user_prompt = f"""
    현재 쟁점: {issue} ({info['title']}), 진행 라운드: {r_num}/{MAX_ROUNDS}
    쟁점 질문: {info['question']}

    찬성(Optimus)의 최근 발언:
    {clip(pro['text'], 700) if pro else '(없음)'}

    반대(Criticus)의 최근 발언:
    {clip(con['text'], 700) if con else '(없음)'}

    이 쟁점 카드의 단서(caveat) 목록:
    {caveats}

    사회자 임무:
    1. 쟁점 질문에 직접 답하는 데 필요한, 양측이 아직 입증하지 못한 지점을 각각 하나씩 짚으십시오.
    2. 위 caveat 중 한쪽이 누락하거나 축소한 단서가 있으면 해당 카드 ID와 함께 지적하십시오.
    3. Optimus에게 한 가지, Criticus에게 한 가지 구체적 질문을 던지고, 카드 ID와 수치(카드에 있는 값)를 근거로 답하도록 요구하십시오.
    4. 이번 쟁점 질문({issue})에서 벗어나지 마십시오. (350자 이내)
    """
    speech = call_gemini(HARMONY_SYSTEM_PROMPT, user_prompt)
    DebateLogger.speech("harmony", "사회자 Harmony", f"중재 질의 - {issue}", speech)
    return {"claims": [_claim(f"claim_h_{issue}_{r_num}", speech, issue, r_num)], "stage": "cross"}


LEDGER_PROMPT = """아래는 한 쟁점에 대한 토론 전문입니다. 중립적 사회자로서 JSON으로만 정리하십시오.
{"consensus": ["양측이 모두 인정한 사실 (카드 ID 포함)"],
 "factual_conflict": ["같은 사안에 대해 수치·사실 주장이 충돌하는 지점"],
 "value_divergence": ["같은 수치를 다르게 해석하는 가치관·해석 차이"]}
각 항목은 한 문장이며, 토론에 실제로 나온 내용만 쓰십시오. 없으면 빈 배열."""


def summarize_issue(state: DebateState, issue: str, rounds: int, reason: str) -> dict:
    """쟁점 종료 시 Harmony가 합의/사실충돌/가치차이를 정리해 ledger 항목을 만든다."""
    claims = [c for c in state["claims"] if c["issue"] == issue and c["speaker"] in ("optimus", "criticus")]
    transcript = "\n\n".join(f"[{c['speaker']} R{c['round_in_issue']} 검증:{c['check']}]\n{c['text']}" for c in claims)
    data = call_gemini_json(LEDGER_PROMPT, f"쟁점: {issue} {ISSUES[issue]['title']}\n\n{transcript}",
                            required=["consensus", "factual_conflict", "value_divergence"], temperature=0.1)
    return {
        "issue": issue, "rounds": rounds, "stop_reason": reason,
        "consensus": data["consensus"], "factual_conflict": data["factual_conflict"],
        "value_divergence": data["value_divergence"],
        "concessions": [{"speaker": c["speaker"], "reason": c["concession_reason"]} for c in claims if c["concession"]],
    }
