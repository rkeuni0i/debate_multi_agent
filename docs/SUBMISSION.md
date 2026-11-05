# 제출 설명서: LangGraph 기반 AI 다자간 심층 토의 시스템

## 1. 한 줄 요약

사회자·찬성·반대·검증자·판정자 5개 에이전트가 **동결된 증거 카드 20개**만을 근거로 3개 쟁점을 토의하고, 발언마다 **인용·수치를 코드로 검증**한 뒤, 이름을 가린 판정자가 쟁점별 [합의 / 증거 부족 / 가치관 차이] 리포트를 만든다.

- 주제: "AI 시대는 과연 사람을 이롭게 하는가?"
- 쟁점: Q1 생산성·노동 강도 / Q2 향후 10년 한국 고용 총량 / Q3 청년·주니어 고용
- 설계 기준: `debate_plan.html` 기획안

## 2. 실행 방법

```bash
uv run python main.py                            # 토의 실행 (약 7분, Vertex AI Gemini 2.5 Flash)
uv run python -m unittest discover -s tests -t .  # 테스트 16개 (LLM 호출 없음)
```

산출물: `reports/final_debate_report.md`(최종 리포트), `reports/transcript_*.json`(전체 발언·검증 결과·Ledger), `docs/sample_run_log.txt`(실제 실행 로그 1회분).

## 3. 흐름

```
Harmony 발제 → [Optimus 입론 ∥ Criticus 입론](서로 비공개) → Verifier
  → 쟁점 Q1 → Q2 → Q3 반복:
       Harmony 질의 → Optimus → Verifier → Criticus → Verifier → Ledger
       · Verifier 불일치 → 해당 발언 1회 정정 후 재검증
       · 새 증거가 없거나 2라운드가 끝나면 쟁점 종료, Harmony가 합의/사실충돌/가치차이를 Ledger에 기록
  → Judge(토론자 A/B 블라인드) → 리포트 + 검증 요약 부록
```

## 4. 기획안 대비 구현 현황

| 기획안 항목 | 상태 | 구현 |
|---|---|---|
| 5인 에이전트(Harmony/Optimus/Criticus/Verifier/Judge) | 구현 | `src/nodes/` |
| 동결된 공용 증거 풀(20개), 풀에 없는 연구 인용 금지 | 구현 | `data/evidence_pool.json`, 프롬프트에 카드 전문 주입 |
| Round 0 독립 입론(상호 비공개, 병렬) | 구현 | 그래프 병렬 분기 후 합류, Round 0 양보는 무효 처리 |
| Verifier ok / mismatch / no_evidence 태깅 | 구현 | `src/verification.py` (LLM 없이 결정론적 수치 대조) |
| mismatch 시 수치 정정 기회 1회 | 구현 | `fix_claims` 노드, 발언 id당 1회 |
| 쟁점별 Debate Ledger | 구현 | 쟁점 종료 시 Harmony가 요약 → Judge 입력 |
| 적응적 종료(쟁점당 최대 2회, 새 증거 없으면 조기 종료) | 구현 | `ledger_update` |
| 근거 있는 양보 허용, 형식적 양보·억지 버티기 금지 | 구현 | 양보 시 근거 사유 필수 요구, `agreement_level = 0.4` 임계치 프롬프트 규칙 반영 (`src/nodes/debater.py`) |
| 블라인드 Judge, 3분할 매트릭스, 정책 시사점 | 구현 | 이름을 A/B로 치환, 검증 실패 발언은 근거 제외, 정책 제언은 카드 근거 병기 |
| M3 "자동화형 vs 증강형" 프레임으로 사회자가 쟁점 좁히기 | 부분 | 프롬프트에 규정. 실행 시 적용 여부는 사회자 발언으로만 확인 가능 |
| `tests/test_verifier.py`, `test_graph_flow.py` | 구현 | `test_verification.py`(9), `test_graph_flow.py`(7) 전체 16개 통과 (상세: `docs/TESTING.md`) |
| `src/utils.py` 로깅·스트리밍 포맷터 | 구현 | `src/utils.py` (`DebateLogger`, Windows CP949 인코딩 자동 보정) |

## 5. 핵심 설계 포인트

1. **토론자가 카드를 직접 본다.** 쟁점별 카드 8~9개를 요약+단서 전문으로 주입하고 "카드에 있는 수치만, 수치 문장마다 출처 ID 표기"를 규칙으로 둔다. 초기 버전에서는 카드를 주지 않아 모델이 수치를 지어냈다(P2에 없는 20%, C4에 없는 11.1% 등).
2. **검증은 LLM이 아닌 코드가 한다.** 문장 단위로 수치(%, %p, 만 개, 개월 등)를 뽑아 그 문장이 인용한 카드의 summary/caveat와 대조한다. 다른 카드에 있는 수치면 "해당 수치는 M1 카드에 있습니다"라고 힌트까지 준다. 초기 로그에서 나온 가짜 수치 중 주요 5건(P2의 20%, P1에 잘못 붙은 25.1%, C1의 12%p, C2의 11.5%, C4의 11.1%)은 테스트 케이스로 고정했다.
3. **발언 직후 검증 → 정정 → 재검증.** Criticus는 검증을 통과한 Optimus 발언만 보고 반박한다.
4. **판정 입력을 정화한다.** 이름·입장 표지를 제거하고, 검증 실패 발언에는 경고를 붙이며, 근거 카드를 같이 넘긴다.
5. **LLM 없이 흐름을 테스트한다.** 가짜 Gemini로 정정 루프, 조기 종료, 블라인드를 자동 확인한다.

## 6. 실행 결과 (docs/sample_run_log.txt, 2026-11-04 1회 실행)

- 토론자 발언 14건 전부 검증 통과. 정정 요청 1건: Optimus가 "C1 caveat" 같은 존재하지 않는 ID를 인용 → 정정 후 통과.
- 쟁점 3개 모두 2라운드 진행, Ledger 기록 완료. 리포트에 토론자 이름·찬반 표지 없음.
- 같은 방식으로 이전 버전(카드 미주입·ID만 확인)을 돌렸을 때는 카드에 없는 수치가 담긴 발언이 최소 5건 있었으나 전부 "검증 완료"로 표시됐다.

## 7. 한계 (정직하게)

- **의미 검증은 하지 않는다.** 수치와 출처 ID는 코드가 맞춰 보지만, 카드의 의미를 반대로 해석하는 것(예: M1의 "25.6만 개 감소 추정"을 "총량 감소가 아니라 직무 대체 효과"라고 풀이)은 통과한다.
- Judge의 "합의 완료" 항목에 일부 해석이 섞일 수 있다. 정책 제언의 카드 근거 표기도 코드로 검증하지 않는다.
- 단일 모델(Gemini 2.5 Flash)이 모든 역할을 맡는다. 같은 모델끼리의 동조 경향을 별도로 측정하지 않았다.
- 실행마다 결과가 다르다(temperature 0.3). 라운드 수와 정정 횟수도 달라질 수 있다.

## 8. 증거 풀 확장 파이프라인 (선택 기능, 토의 실행과 분리)

`src/research/`: Gemini Deep Research(Vertex, location=global)로 후보를 넓게 찾고 → ego-browser로 필요한 후보만 열어 확인한다. 증거 풀(`evidence_pool.json`)은 자동으로 바뀌지 않으며, 후보는 `data/evidence_candidates.json`에만 저장된다.

- 실행해 본 범위: Q2에 대해서만 Deep Research를 실행(약 20분)해 후보 6건을 추출. 보고서에 출처 URL이 없어 검색어로 ego-browser 검색을 수행(4건 링크 수집, 2건 결과 없음).
- 확인된 것: NABO 보고서(P8의 출처) 페이지가 열리고 제목 "[경제현안분석 제110호] 생성형 AI의 노동시장 영향", 작성일 2026-09-18이 일치. 단 21.2%, 1,512명 같은 수치는 PDF 안에 있어 아직 대조하지 못함.
- 미완료: Q1·Q3 Deep Research 미실행, Acemoglu 링크는 로딩 시간 초과, 수집한 후보를 증거 카드로 승격하는 절차(사람 검수)는 미구현.
- ego-browser 0.6.2.5는 `task.finish()` 직후 오류를 낸다. 결과 저장 후 오류만 무시하도록 처리했다.
