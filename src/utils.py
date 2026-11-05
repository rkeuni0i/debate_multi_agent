"""토의 시스템 전용 콘솔 포맷터 및 로깅 유틸리티 (기획안 명세: src/utils.py)"""
import sys
from typing import List, Optional

# Windows 환경(CP949)에서 유니코드/이모지 출력 에러 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class DebateLogger:
    """토의 진행 상황을 시각적으로 구조화하여 출력하는 콘솔 포맷터"""

    ICONS = {
        "harmony": "⚖️",
        "optimus": "💡",
        "criticus": "⚠️",
        "verifier": "🔍",
        "judge": "🏆",
        "system": "🏛️",
        "ledger": "📋",
        "fix": "🛠️",
    }

    @classmethod
    def section(cls, title: str, char: str = "=") -> None:
        """대구분 헤더 출력"""
        border = char * 80
        print(f"\n{border}")
        print(f"{title}")
        print(f"{border}")

    @classmethod
    def speech(cls, speaker: str, name: str, title: str, text: str,
               ids: Optional[List[str]] = None, concession: Optional[str] = None) -> None:
        """토론자 및 사회자 발언 출력"""
        icon = cls.ICONS.get(speaker, "🗣️")
        conc = f", 양보: {concession}" if concession else ""
        cites = f" (인용: {ids}{conc})" if ids is not None else ""
        print(f"\n{icon} [{name} {title}]:\n{text}{cites}")

    @classmethod
    def verify(cls, speaker: str, status: str, ids: List[str], notes: List[str]) -> None:
        """검증자(Verifier) 판정 결과 출력"""
        if status == "ok":
            print(f"  🔍 [Verifier]: {speaker} 발언 - ✅ 인용·수치 대조 통과 ({', '.join(ids)})")
        else:
            print(f"  🔍 [Verifier]: {speaker} 발언 - ❌ {status}")
            for n in notes:
                print(f"       · {n}")

    @classmethod
    def fix_request(cls, speaker: str, cid: str, notes: List[str]) -> None:
        """수치 불일치 시 정정 안내 출력"""
        print(f"\n🛠️ [정정 요청]: {speaker} ({cid}) - {'; '.join(notes)}")

    @classmethod
    def ledger(cls, text: str) -> None:
        """Ledger 기록 및 라운드 전환 안내 출력"""
        print(f"\n[Ledger]: {text}")

    @classmethod
    def info(cls, text: str) -> None:
        """일반 시스템 알림 출력"""
        print(f"\n{text}")

