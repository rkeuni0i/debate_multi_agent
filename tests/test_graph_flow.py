"""그래프 상태 전이 테스트: 가짜 LLM으로 실제 API 호출 없이 전체 흐름을 검증한다."""
import json
import types
import unittest
from unittest import mock

import src.llm as llm
from src.graph import build_debate_graph
from src.issues import ISSUES

with open("data/evidence_pool.json", encoding="utf-8") as f:
    POOL = json.load(f)


class _Resp:
    def __init__(self, text):
        self.text = text


class FakeGemini:
    """첫 Optimus 발언은 일부러 가짜 수치(P2의 20%)를 내고, 정정 요청이 오면 올바른 수치로 답한다."""

    def __init__(self):
        self.judge_prompts = []
        self.fix_requests = 0

    def generate_content(self, model, contents, config):
        sysmsg = config.get("system_instruction", "")
        if "토의 규칙 (반드시" in sysmsg:  # 토론자
            if "[정정 요청]" in contents:
                self.fix_requests += 1
                body = {"text": "해결 건수가 15% 증가했습니다(P1). 단서: 단일 기업 한정.", "evidence_ids": ["P1"]}
            elif "혁신주의자" in sysmsg:
                body = {"text": "적극 활용 시 20%까지 향상됩니다(P2).", "evidence_ids": ["P2"]}
            else:
                body = {"text": "청년 일자리 21.1만 개가 감소했습니다(C3). 단서: AI 단독 요인 아님.",
                        "evidence_ids": ["C3"], "concession": True, "concession_reason": "근거 있음"}
            return _Resp(json.dumps(body, ensure_ascii=False))
        if "consensus" in sysmsg:  # Ledger 요약
            return _Resp(json.dumps({"consensus": ["c"], "factual_conflict": [], "value_divergence": ["v"]}))
        if "최종 '판정자" in sysmsg:
            self.judge_prompts.append(contents)
        return _Resp("(가짜 응답)")


def _initial_state():
    return {
        "resolution": "테스트 명제", "issues": list(ISSUES), "evidence_pool": POOL, "openings": {}, "claims": [],
        "ledger": [], "fixed_ids": [], "issue_idx": 0, "round_in_issue": 1, "stage": "start",
        "stop_reason": None, "final_report": None,
    }


class GraphFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeGemini()
        fake_client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=cls.fake.generate_content))
        with mock.patch.object(llm, "client", fake_client), mock.patch("time.sleep"):
            cls.state = build_debate_graph().invoke(_initial_state(), config={"recursion_limit": 120})

    def test_all_issues_recorded_in_ledger(self):
        self.assertEqual([e["issue"] for e in self.state["ledger"]], list(ISSUES))
        self.assertEqual(self.state["stop_reason"], "completed")

    def test_mismatch_is_fixed_once_and_passes(self):
        self.assertGreater(self.fake.fix_requests, 0)
        self.assertTrue(self.state["fixed_ids"])
        optimus = [c for c in self.state["claims"] if c["speaker"] == "optimus"]
        self.assertTrue(all(c["check"] == "ok" for c in optimus))

    def test_fix_is_limited_to_one_attempt(self):
        # 발언 id별로 정정은 최대 1회만 허용된다
        self.assertEqual(len(self.state["fixed_ids"]), len(set(self.state["fixed_ids"])))

    def test_round0_concession_is_ignored(self):
        opening = next(c for c in self.state["claims"] if c["id"] == "claim_con_open")
        self.assertFalse(opening["concession"])

    def test_early_stop_when_no_new_evidence(self):
        for e in self.state["ledger"]:
            self.assertEqual(e["rounds"], 1)
            self.assertIn("조기 종료", e["stop_reason"])

    def test_judge_is_blind(self):
        prompt = self.fake.judge_prompts[0]
        self.assertNotIn("Optimus", prompt)
        self.assertNotIn("Criticus", prompt)
        self.assertIn("토론자 A", prompt)

    def test_report_has_verification_appendix(self):
        self.assertIn("부록: 토의 진행·검증 요약", self.state["final_report"])


if __name__ == "__main__":
    unittest.main()
