from langgraph.graph import StateGraph, START, END
from src.state import DebateState
from src.issues import MAX_ROUNDS
from src.nodes.moderator import harmony_frame, harmony_cross_examine, summarize_issue
from src.nodes.debater import optimus_opening, criticus_opening, optimus_rebuttal, criticus_rebuttal, fix_claims
from src.nodes.verifier import verifier_check, route_after_verify, NEXT_AFTER_VERIFY
from src.nodes.judge import judge_synthesize
from src.utils import DebateLogger

DEBATERS = ("optimus", "criticus")


def _cited_before(state: DebateState, issue: str, r_num: int) -> set:
    """이번 라운드 이전에 토론자들이 이미 인용한 증거 ID 전체"""
    return {i for c in state["claims"] if c["speaker"] in DEBATERS
            and not (c["issue"] == issue and c["round_in_issue"] >= r_num)
            for i in c["evidence_ids"]}


def ledger_update(state: DebateState) -> dict:
    """라운드 종료 처리: 새 증거가 없거나 최대 라운드면 쟁점을 닫고 ledger에 기록, 아니면 다음 라운드로."""
    issue_idx, r_num = state["issue_idx"], state["round_in_issue"]
    issue = state["issues"][issue_idx]
    this_round = {i for c in state["claims"] if c["speaker"] in DEBATERS
                  and c["issue"] == issue and c["round_in_issue"] == r_num for i in c["evidence_ids"]}
    new_evidence = this_round - _cited_before(state, issue, r_num)

    if r_num >= MAX_ROUNDS:
        reason = f"최대 {MAX_ROUNDS}라운드 도달"
    elif not new_evidence:
        reason = "새로운 증거 없음(조기 종료)"
    else:
        DebateLogger.ledger(f"{issue} Round {r_num} 종료 — 새 증거 {sorted(new_evidence)} 등장, 다음 라운드 진행")
        return {"round_in_issue": r_num + 1}

    DebateLogger.ledger(f"{issue} 종료 ({reason}) — 사회자 정리 작성 중...")
    entry = summarize_issue(state, issue, r_num, reason)
    return {"ledger": [entry], "issue_idx": issue_idx + 1, "round_in_issue": 1}


def route_next_step(state: DebateState) -> str:
    """남은 쟁점이 있으면 harmony_cross(다음 라운드/쟁점), 없으면 judge"""
    if state["issue_idx"] >= len(state["issues"]):
        return "judge"
    return "cross_examine"


def build_debate_graph():
    """LangGraph StateGraph 빌더 함수"""
    builder = StateGraph(DebateState)

    builder.add_node("harmony_frame", harmony_frame)
    builder.add_node("optimus_opening", optimus_opening)
    builder.add_node("criticus_opening", criticus_opening)
    builder.add_node("verifier", verifier_check)      # 모든 단계에서 공용
    builder.add_node("fix_claims", fix_claims)
    builder.add_node("harmony_cross", harmony_cross_examine)
    builder.add_node("optimus_rebuttal", optimus_rebuttal)
    builder.add_node("criticus_rebuttal", criticus_rebuttal)
    builder.add_node("ledger_update", ledger_update)
    builder.add_node("judge", judge_synthesize)

    # Round 0: 독립 입론 병렬 실행 → 둘 다 끝나면 Verifier
    builder.add_edge(START, "harmony_frame")
    builder.add_edge("harmony_frame", "optimus_opening")
    builder.add_edge("harmony_frame", "criticus_opening")
    builder.add_edge(["optimus_opening", "criticus_opening"], "verifier")

    # 쟁점 루프: 질의 → Optimus → Verifier → Criticus → Verifier → Ledger
    builder.add_edge("harmony_cross", "optimus_rebuttal")
    builder.add_edge("optimus_rebuttal", "verifier")
    builder.add_edge("criticus_rebuttal", "verifier")
    builder.add_edge("fix_claims", "verifier")

    # Verifier 이후: 불일치 → 정정(1회), 통과 → stage에 따른 다음 노드
    builder.add_conditional_edges(
        "verifier", route_after_verify,
        {"fix_claims": "fix_claims", **{v: v for v in set(NEXT_AFTER_VERIFY.values())}},
    )

    builder.add_conditional_edges(
        "ledger_update", route_next_step,
        {"cross_examine": "harmony_cross", "judge": "judge"},
    )
    builder.add_edge("judge", END)

    return builder.compile()
