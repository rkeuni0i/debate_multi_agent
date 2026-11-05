from typing import Annotated, TypedDict, Literal, List, Dict, Any, Optional
import operator

def merge_dict(a: dict, b: dict) -> dict:
    """Round 0 병렬 입론 노드의 출력을 안전하게 병합하는 리듀서 함수"""
    res = dict(a)
    res.update(b)
    return res

def merge_claims(a: List["Claim"], b: List["Claim"]) -> List["Claim"]:
    """Claim ID 기준 중복 제거 및 상태 갱신 리듀서 (정정·검증 결과는 같은 id로 덮어쓴다)"""
    seen = {c["id"]: c for c in a}
    for c in b:
        seen[c["id"]] = c
    return list(seen.values())

class Evidence(TypedDict):
    id: str                    # "P1", "C3", "M1" ...
    side: Literal["pro", "con", "both"]
    source: str
    as_of: str                 # 사용 버전/발행일 (예: "2026.08")
    summary: str
    caveat: str
    url: str
    verified: Literal["primary", "secondary", "unverified"]

class Claim(TypedDict):
    id: str
    speaker: Literal["optimus", "criticus", "harmony", "verifier", "judge"]
    side: Optional[Literal["pro", "con"]]
    issue: Optional[Literal["Q1", "Q2", "Q3"]]
    round_in_issue: int
    text: str
    evidence_ids: List[str]
    check: Literal["pending", "ok", "mismatch", "no_evidence"]
    check_notes: List[str]     # Verifier가 남긴 불일치 사유
    concession: bool           # 상대방 주장을 수용/인정했는지 여부
    concession_reason: Optional[str]

class DebateState(TypedDict):
    resolution: str            # 토의 대명제
    issues: List[str]          # ["Q1", "Q2", "Q3"]
    evidence_pool: Dict[str, Evidence]
    openings: Annotated[Dict[str, str], merge_dict]  # {"pro": "...", "con": "..."}
    claims: Annotated[List[Claim], merge_claims]
    ledger: Annotated[List[Dict[str, Any]], operator.add]  # 쟁점별 합의/사실충돌/가치차이 기록
    fixed_ids: Annotated[List[str], operator.add]    # 정정 기회를 이미 사용한 claim id
    issue_idx: int             # 0: Q1, 1: Q2, 2: Q3
    round_in_issue: int        # 쟁점 내 반론 라운드 (1 ~ MAX_ROUNDS)
    stage: str                 # Verifier 이후 분기에 쓰는 직전 단계: openings | optimus_rebuttal | criticus_rebuttal
    stop_reason: Optional[str]
    final_report: Optional[str]
