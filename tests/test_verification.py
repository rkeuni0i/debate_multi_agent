"""검증기 단위 테스트: uv run python -m unittest discover -s tests -v"""
import json
import unittest

from src.verification import verify_text, extract_numbers

with open("data/evidence_pool.json", encoding="utf-8") as f:
    POOL = json.load(f)


class VerifyTextTest(unittest.TestCase):
    def test_correct_claim_passes(self):
        text = "상담원 생산성이 15% 증가했습니다(P1). 최고 숙련자는 품질이 소폭 하락했습니다."
        self.assertEqual(verify_text(text, ["P1"], POOL)[0], "ok")

    def test_range_and_pp_units(self):
        text = "BOK은 청년 일자리 21.1만 개 감소 중 98.6%가 고노출 업종이라고 봤습니다(C3). AI 범위 밖 과업에서는 19%p 하락했습니다(P2)."
        self.assertEqual(verify_text(text, ["C3", "P2"], POOL)[0], "ok")

    def test_p2_20_percent_is_fabricated(self):
        # 실제 로그: Optimus가 P2에 없는 '20%'를 P2로 인용
        status, notes = verify_text("적극 활용하는 기업은 생산성이 20%까지 향상되었습니다(P2).", ["P2"], POOL)
        self.assertEqual(status, "mismatch")
        self.assertIn("M1", notes[0])  # 20%는 M1 카드에 있다는 힌트

    def test_misattributed_between_cards(self):
        # 실제 로그: 컨설턴트 연구 수치(25.1%)를 P1(상담원)로 인용
        status, _ = verify_text("컨설턴트 작업 속도가 25.1% 향상되었습니다(P1).", ["P1"], POOL)
        self.assertEqual(status, "mismatch")

    def test_fabricated_numbers_from_log(self):
        for text, ids in [
            ("AI 도입 기업의 신규 채용은 12%p 더 감소했습니다(C1).", ["C1"]),
            ("2019년 대비 2023년에 11.5% 감소했습니다(C2).", ["C2"]),
            ("채용 감소율이 2.9%에서 11.1%로 증가했습니다(C4).", ["C4"]),
        ]:
            self.assertEqual(verify_text(text, ids, POOL)[0], "mismatch", text)

    def test_unknown_id(self):
        status, notes = verify_text("연구에 따르면 증가했습니다(P11).", ["P11"], POOL)
        self.assertEqual(status, "mismatch")
        self.assertIn("P11", notes[0])

    def test_no_evidence(self):
        self.assertEqual(verify_text("AI는 좋습니다.", [], POOL)[0], "no_evidence")

    def test_number_untagged_sentence_uses_claim_ids(self):
        self.assertEqual(verify_text("생산성이 15% 증가했습니다.", ["P1"], POOL)[0], "ok")

    def test_extract_numbers_range(self):
        self.assertEqual(extract_numbers("9~10% 감소"), {("9", "%"), ("10", "%")})


if __name__ == "__main__":
    unittest.main()
