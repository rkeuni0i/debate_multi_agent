import json
import os
from datetime import datetime
from src.state import DebateState
from src.graph import build_debate_graph
from src.issues import ISSUES
from src.utils import DebateLogger


def main():
    DebateLogger.section("🏛️ LangGraph 기반 AI 다자간 심층 토의 시스템 시작")

    # 1. 1차 검증 완료된 공용 증거 풀 로드 (freeze)
    with open(os.path.join("data", "evidence_pool.json"), "r", encoding="utf-8") as f:
        evidence_pool = json.load(f)
    print(f"📦 [증거 풀 로드 완료]: 총 {len(evidence_pool)}개 카드 동결 ({', '.join(evidence_pool)})")

    # 2. 초기 DebateState 정의
    initial_state: DebateState = {
        "resolution": "AI 시대는 과연 사람을 이롭게 하는가? (노동 강도 완화 및 생산성 혁신 vs 고용 대체 및 실업률 증가)",
        "issues": list(ISSUES),
        "evidence_pool": evidence_pool,
        "openings": {},
        "claims": [],
        "ledger": [],
        "fixed_ids": [],
        "issue_idx": 0,
        "round_in_issue": 1,
        "stage": "start",
        "stop_reason": None,
        "final_report": None,
    }

    # 3. 그래프 컴파일 및 실행 (쟁점 루프와 정정 단계가 있어 기본 recursion_limit(25)로는 부족하다)
    app = build_debate_graph()
    DebateLogger.info("🚀 토의 그래프 실행 파이프라인 가동...")
    final_state = app.invoke(initial_state, config={"recursion_limit": 120})

    # 4. 산출물 저장 (최신본 + 타임스탬프 기록)
    os.makedirs("reports", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with open("reports/final_debate_report.md", "w", encoding="utf-8") as f:
        f.write(final_state["final_report"])
    with open(f"reports/transcript_{stamp}.json", "w", encoding="utf-8") as f:
        json.dump({"claims": final_state["claims"], "ledger": final_state["ledger"]}, f, ensure_ascii=False, indent=2)

    deb = [c for c in final_state["claims"] if c["speaker"] in ("optimus", "criticus")]
    DebateLogger.section("✨ 전체 토의 프로세스 완료!")
    print(f"- 토론자 발언: {len(deb)}건 (검증 통과 {sum(c['check'] == 'ok' for c in deb)}건, 정정 사용 {len(final_state['fixed_ids'])}건)")
    print(f"- 최종 리포트: reports/final_debate_report.md")
    print(f"- 발언 기록: reports/transcript_{stamp}.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
