"""발언의 인용·수치를 공용 증거 풀과 결정론적으로 대조한다 (LLM 호출 없음).

규칙
- 발언이 인용한 evidence_id는 풀에 존재해야 한다.
- 발언 속 수치(%, %p, 만 개, 개월 등)는 인용한 카드의 summary/caveat에 있어야 한다.
- 문장에 (P1)처럼 카드 태그가 있으면 그 문장의 수치는 해당 카드에 있어야 한다. 태그가 없으면 발언 전체 인용 카드가 허용 범위다.
"""
import re
from typing import Dict, List, Set, Tuple

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"%p|%|만\s?개|만\s?명|개월|배|억|조"
NUMBER_RE = re.compile(rf"({_NUM})(?:\s*[~∼–]\s*({_NUM}))?\s*({_UNIT})")
TAG_RE = re.compile(r"(?<![A-Za-z0-9])([PCM]\d{1,2})(?!\d)")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")

Number = Tuple[str, str]  # (정규화된 값, 정규화된 단위)


def _norm_value(v: str) -> str:
    return f"{float(v.replace(',', '')):g}"


def _norm_unit(u: str) -> str:
    u = re.sub(r"\s", "", u)
    return "%" if u == "%p" else u


def extract_numbers(text: str) -> Set[Number]:
    found: Set[Number] = set()
    for m in NUMBER_RE.finditer(text):
        unit = _norm_unit(m.group(3))
        for g in (m.group(1), m.group(2)):
            if g:
                found.add((_norm_value(g), unit))
    return found


def card_numbers(card: dict) -> Set[Number]:
    return extract_numbers(f"{card.get('summary', '')} {card.get('caveat', '')}")


def inline_tags(text: str) -> Set[str]:
    return set(TAG_RE.findall(text))


def _fmt(n: Number) -> str:
    return f"{n[0]}{n[1]}"


def verify_text(text: str, evidence_ids: List[str], pool: Dict[str, dict]) -> Tuple[str, List[str]]:
    """반환: (status, notes). status: ok | mismatch | no_evidence"""
    claim_ids = set(evidence_ids) | inline_tags(text)
    if not claim_ids:
        return "no_evidence", ["인용한 evidence_id가 없습니다."]

    notes: List[str] = []
    unknown = sorted(i for i in claim_ids if i not in pool)
    if unknown:
        notes.append(f"증거 풀에 없는 ID를 인용했습니다: {', '.join(unknown)}")
    valid_claim_ids = claim_ids & set(pool)

    cache = {i: card_numbers(pool[i]) for i in pool}
    for sent in SENT_SPLIT_RE.split(text):
        nums = extract_numbers(sent)
        if not nums:
            continue
        allowed = (inline_tags(sent) & set(pool)) or valid_claim_ids
        allowed_nums: Set[Number] = set().union(*(cache[i] for i in allowed)) if allowed else set()
        for n in sorted(nums - allowed_nums):
            owners = sorted(i for i, nn in cache.items() if n in nn)
            hint = f"해당 수치는 {', '.join(owners)} 카드에 있습니다" if owners else "어떤 카드에도 없는 수치입니다"
            notes.append(f"수치 {_fmt(n)}이(가) 인용 카드({', '.join(sorted(allowed))})에 없습니다. {hint}.")
    return ("mismatch" if notes else "ok"), notes
