"""
Urban-MicroGrid | LLM 호출부

여기서 하는 일은 **프롬프트를 모델에 넘기고 문장을 받아오는 것** 뿐이다.
사실표 조립·표현 규칙·숫자 검증은 briefing.py 에 있다.
모델을 바꾸려면 이 파일의 어댑터 하나만 추가하면 된다.

키가 없거나 SDK 가 없으면 예외가 아니라 '아직 못 함'으로 처리된다
(API 가 503 + status:"pending" 으로 내려보낸다).
"""
import os

from . import config as C


class LLMUnavailable(Exception):
    """호출 자체가 불가능한 상태 — 키 미설정, SDK 미설치."""


class LLMFailed(Exception):
    """호출은 했으나 실패 — 네트워크·쿼터·안전필터."""


def api_key():
    for name in C.LLM_API_KEY_ENVS:
        v = os.environ.get(name)
        if v:
            return v
    return None


def status():
    """/api/meta 에서 '지금 브리핑을 만들 수 있는가'를 알려주기 위한 것."""
    if not api_key():
        return "pending", f"{C.LLM_API_KEY_ENVS[0]} 환경변수를 설정하면 활성화됩니다"
    try:
        _sdk()
    except LLMUnavailable as e:
        return "pending", str(e)
    return "ready", None


def _sdk():
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise LLMUnavailable(
            "google-genai 가 설치되어 있지 않습니다 (pip install google-genai)")
    return genai, types


# ══════════════════════════════════════════════════════════
#  Gemini
# ══════════════════════════════════════════════════════════
def _generate_gemini(system, user):
    genai, types = _sdk()
    key = api_key()
    if not key:
        raise LLMUnavailable(
            f"{C.LLM_API_KEY_ENVS[0]} 환경변수가 없습니다")

    # HttpOptions.timeout 은 밀리초 단위다.
    # SDK 버전에 따라 인자를 안 받을 수 있어 실패해도 호출은 계속되게 둔다.
    try:
        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=int(C.LLM_TIMEOUT_S * 1000)))
    except Exception:
        client = genai.Client(api_key=key)

    try:
        resp = client.models.generate_content(
            model=C.LLM_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=C.LLM_MAX_OUTPUT_TOKENS,
                temperature=C.LLM_TEMPERATURE,
            ),
        )
    except Exception as e:                      # 네트워크·인증·쿼터
        raise LLMFailed(f"{type(e).__name__}: {e}")

    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        # 안전필터에 걸렸거나 max_output_tokens 에서 잘린 경우
        reason = None
        for cand in (getattr(resp, "candidates", None) or []):
            reason = getattr(cand, "finish_reason", None)
            break
        raise LLMFailed(f"모델이 빈 응답을 반환했습니다 (finish_reason={reason})")

    usage = getattr(resp, "usage_metadata", None)
    return {
        "text": text,
        "provider": "gemini",
        "model": C.LLM_MODEL,
        "usage": {
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
        } if usage else None,
    }


_ADAPTERS = {"gemini": _generate_gemini}


def generate(system, user):
    """프롬프트를 모델에 넘기고 결과를 받는다."""
    fn = _ADAPTERS.get(C.LLM_PROVIDER)
    if fn is None:
        raise LLMUnavailable(
            f"지원하지 않는 provider 입니다: {C.LLM_PROVIDER} "
            f"(가능: {', '.join(_ADAPTERS)})")
    return fn(system, user)
