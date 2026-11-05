from typing import Dict, Iterable, List, Optional
from src.state import Claim


def render_cards(pool: Dict[str, dict], ids: Iterable[str]) -> str:
    """프롬프트에 넣을 증거 카드 텍스트 (요약과 단서 전문)"""
    lines = []
    for i in ids:
        c = pool[i]
        lines.append(f"[{i}] {c['source']}\n  요약: {c['summary']}\n  단서(caveat): {c['caveat']}")
    return "\n".join(lines)


def latest_claim(claims: List[Claim], speaker: str, issue: Optional[str] = None) -> Optional[Claim]:
    """speaker의 가장 최근 발언. issue를 주면 해당 쟁점 발언만 대상으로 한다."""
    for c in reversed(claims):
        if c["speaker"] == speaker and (issue is None or c["issue"] == issue):
            return c
    return None


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"
