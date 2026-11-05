# AI 다자간 심층 토의 시스템 (LangGraph)

주제: "AI 시대는 과연 사람을 이롭게 하는가?" — 사회자·찬성·반대·검증자·판정자 5개 에이전트가 검증된 증거 카드(20개)만 근거로 토의하고, 쟁점별 [합의 / 증거 부족 / 가치관 차이] 매트릭스 리포트를 만든다. 설계 기준은 `debate_plan.html`.

## 실행

```bash
uv run python main.py                           # 토의 실행 → reports/final_debate_report.md
uv run python -m unittest discover -s tests -t . # 검증기 단위 테스트(LLM 호출 없음)
```

Vertex AI(ADC 인증)를 사용한다. `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_REGION` 환경변수로 변경 가능.

제출용 설명(기획안 대비 구현 현황, 실행 결과, 한계)은 `docs/SUBMISSION.md`, 실제 실행 로그는 `docs/sample_run_log.txt`, 상세 테스팅 명세 및 검증 보고서는 `docs/TESTING.md`.

## 흐름

```
Harmony 발제 → [Optimus 입론 ∥ Criticus 입론](서로 비공개) → Verifier
  → 쟁점 Q1→Q2→Q3 반복:
      Harmony 질의 → Optimus → Verifier → Criticus → Verifier → Ledger
      (Verifier 불일치 시 해당 발언 1회 정정, 새 증거 없거나 2라운드면 쟁점 종료)
  → Judge(A/B 블라인드) → 리포트
```

- **Verifier**: LLM 없이 결정론적으로 검증한다. 인용 ID가 풀에 있는지, 발언 속 수치(%, %p, 만 개 등)가 인용 카드의 summary/caveat에 있는지 확인한다 (`src/verification.py`).
- **Ledger**: 쟁점 종료 시 Harmony가 합의/사실 충돌/가치 차이를 정리해 Judge에 전달한다.
- **Judge**: 토론자 이름을 A/B로 치환하고, 검증 실패 발언의 수치는 근거로 쓰지 않도록 표시한다.

## 구조

| 경로 | 역할 |
|---|---|
| `main.py` | 실행·산출물 저장 |
| `src/state.py` | `DebateState`, `Claim`, `Evidence` |
| `src/graph.py` | 그래프, Ledger/종료 규칙 |
| `src/issues.py` | 쟁점 질문과 쟁점별 사용 카드 |
| `src/nodes/` | moderator, debater, verifier, judge |
| `src/verification.py` | 수치 대조 로직 |
| `src/utils.py` | 터미널 로깅 및 스트리밍 포맷터 (Windows UTF-8 대응) |
| `docs/TESTING.md` | 테스팅 전략, 단위·통합·E2E 테스트 케이스 및 검증 보고서 |
| `docs/SUBMISSION.md` | 기획안 대비 구현 현황, 실행 결과 및 제출 설명서 |
| `data/evidence_pool.json` | 동결된 증거 카드 20개 |
| `src/research/` | (선택) Deep Research + ego-browser로 새 증거 후보 수집 |
| `.env.example` | Vertex AI 환경 변수 설정 템플릿 |
