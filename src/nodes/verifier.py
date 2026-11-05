from src.state import DebateState
from src.verification import verify_text
from src.utils import DebateLogger

DEBATERS = ("optimus", "criticus")

# Verifier 통과 후 다음 노드 (stage = 직전에 실행된 발언 단계)
NEXT_AFTER_VERIFY = {
    "openings": "harmony_cross",
    "optimus_rebuttal": "criticus_rebuttal",
    "criticus_rebuttal": "ledger_update",
}


def verifier_check(state: DebateState) -> dict:
    """아직 검증되지 않은(pending) 토론자 발언을 증거 풀과 대조해 check를 태깅한다."""
    pool = state["evidence_pool"]
    updated = []
    for claim in state["claims"]:
        if claim["speaker"] not in DEBATERS or claim["check"] != "pending":
            continue
        status, notes = verify_text(claim["text"], claim["evidence_ids"], pool)
        updated.append({**claim, "check": status, "check_notes": notes})
        DebateLogger.verify(claim["speaker"], status, claim["evidence_ids"], notes)
    return {"claims": updated}


def route_after_verify(state: DebateState) -> str:
    """불일치 발언이 있고 아직 정정 기회를 쓰지 않았다면 정정 노드로, 아니면 다음 단계로 보낸다."""
    done = set(state["fixed_ids"])
    needs_fix = any(c["speaker"] in DEBATERS and c["check"] in ("mismatch", "no_evidence") and c["id"] not in done
                    for c in state["claims"])
    return "fix_claims" if needs_fix else NEXT_AFTER_VERIFY[state["stage"]]
