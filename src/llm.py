import os
import json
import re
import time
from google import genai
from typing import Dict, Any, Iterable

# Vertex AI ADC 기반 GenAI 클라이언트 싱글톤
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
LOCATION = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

def call_gemini(system_prompt: str, user_prompt: str, model: str = "gemini-2.5-flash",
                temperature: float = 0.3, json_mode: bool = False, retries: int = 5) -> str:
    """Gemini API 호출 유틸리티 (빈 응답/네트워크 단절 등 일시 오류는 지수 백오프로 최대 5회 재시도)"""
    config = {
        "system_instruction": system_prompt,
        "temperature": temperature,
        "max_output_tokens": 8192,
    }
    if json_mode:
        config["response_mime_type"] = "application/json"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.models.generate_content(model=model, contents=user_prompt, config=config)
            text = (response.text or "").strip()
            if text:
                return text
            last_err = ValueError("빈 응답")
        except Exception as e:  # 네트워크/소켓 단절/쿼터 등 일시 오류
            last_err = e
        time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError(f"Gemini 호출 {retries}회 실패: {last_err}")

def extract_json(text: str) -> Dict[str, Any]:
    """응답 텍스트에서 JSON 객체 안전하게 추출 (실패 시 빈 dict)"""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                data = json.loads(text[start:end + 1])
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}

def call_gemini_json(system_prompt: str, user_prompt: str, required: Iterable[str] = (), attempts: int = 3,
                     **kwargs) -> Dict[str, Any]:
    """JSON 모드로 호출하고 필수 키가 모두 있을 때까지 재시도한다. 끝내 실패하면 예외."""
    required = list(required)
    for _ in range(attempts):
        data = extract_json(call_gemini(system_prompt, user_prompt, json_mode=True, **kwargs))
        if data and all(k in data for k in required):
            return data
    raise RuntimeError(f"유효한 JSON 응답을 받지 못했습니다 (필수 키: {required})")
