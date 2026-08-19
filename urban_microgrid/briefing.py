"""
Urban-MicroGrid | AI 브리핑 — 사실표 · 프롬프트 · 검증

설계
────────────────────────────────────────────────────────────
모델에게 '분석'을 시키지 않는다. 분석은 이미 파이프라인이 끝냈다.
모델이 하는 일은 **실측값을 사람 문장으로 옮기는 것** 하나다.

    ① build_facts   실측 산출물에서 사실표를 만든다 (숫자는 여기서만 나온다)
    ② build_prompt  사실표 + 표현 규칙을 프롬프트로 조립한다
    ③ verify        생성된 문장에 사실표에 없는 숫자가 섞였는지 검사한다

③ 이 이 파일의 존재 이유다. LLM 은 그럴듯한 숫자를 지어낼 수 있고,
이 프로젝트에서 그건 '측정하지 않은 수치를 만들지 않는다'는 규칙 위반이다.
"""
import json
import re

from . import config as C

# 문서에서 쓰는 유니코드 마이너스(−)를 ASCII 로 맞춘다
_MINUS = {"−": "-", "–": "-"}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# 일상 표현에 등장하는 작은 수는 검증에서 제외한다
# ("3분의 1", "2개 동", "10곳 중 8곳", 시각 0~24)
_SAFE_MAX = 24


# ══════════════════════════════════════════════════════════
#  ① 사실표
# ══════════════════════════════════════════════════════════
def build_facts(summaries, weather=None):
    """
    summaries: [동 상세 응답, ...]  (serialize.build_dong_summary 결과)
    weather:   그날의 기상 요약 (선택)

    반환값의 숫자만이 브리핑에 등장할 수 있는 유일한 숫자다.
    """
    dongs = []
    for s in summaries:
        mc, dm, cl, pk = (s["microclimate"], s["demand"],
                          s["cooling"], s["peak"])
        dongs.append({
            "이름": s["name"],
            "도시열지수": mc.get("heat_index"),
            "도시열등급": mc.get("grade"),
            "불투수_퍼센트": mc["components"]["paved"]["percent"],
            "식생_퍼센트": mc["components"]["green"]["percent"],
            "평소대비_추가사용_퍼센트": dm.get("extra_usage_percent"),
            "야간_추가사용_퍼센트": dm.get("night_percent"),
            "주간_추가사용_퍼센트": dm.get("day_percent"),
            "냉방시작온도": cl.get("switch_on_temp"),
            "1도당_증가율_퍼센트": cl.get("sensitivity"),
            "위험일수": pk.get("risk_days"),
            "전체일수": pk.get("total_days"),
        })

    facts = {
        "분석기간": f"{C.SUMMER_START} ~ {C.SUMMER_END}",
        "지역수": len(dongs),
        "지역": dongs,
        "통계검정": dict(C.PAIRED_TEST_RESULT),
        "자료성격": "프로젝트 예비값 (공식 통계 아님)",
        "미기후_산출기준": C.MICROCLIMATE_BASIS["note"],
    }
    if weather:
        facts["그날의기상"] = {k: v for k, v in weather.items() if v is not None}
    return facts


# ══════════════════════════════════════════════════════════
#  ② 프롬프트
# ══════════════════════════════════════════════════════════
SYSTEM_PROMPT = """당신은 전력수요 분석 대시보드의 브리핑 문구를 쓰는 사람입니다.
분석은 이미 끝났습니다. 당신의 일은 주어진 사실표를 사람이 읽는 문장으로 옮기는 것입니다.

지켜야 할 규칙:
{rules}

출력은 완성된 한국어 문장만 씁니다. 머리말·목록기호·인용부호·마크다운을 쓰지 않습니다."""


def build_prompt(facts, question=None):
    """
    반환: {"system": ..., "user": ...}
    프론트·개발자가 무엇이 모델에 넘어갔는지 그대로 볼 수 있도록 응답에도 실린다.
    """
    rules = "\n".join(f"- {r}" for r in C.BRIEFING_RULES)
    ask = question or (
        "아래 사실표를 바탕으로 대시보드 우측에 넣을 브리핑을 써 주세요. "
        "두 지역의 차이 중 가장 두드러진 것 하나를 골라 서술하고, "
        "마지막 문장에 자료의 한계를 병기하세요."
    )
    user = (f"{ask}\n\n"
            f"[사실표]\n{json.dumps(facts, ensure_ascii=False, indent=2)}")
    return {"system": SYSTEM_PROMPT.format(rules=rules), "user": user}


# ══════════════════════════════════════════════════════════
#  ③ 검증 — 지어낸 숫자 잡기
# ══════════════════════════════════════════════════════════
def _walk_numbers(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_numbers(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, str):
        for m in _NUMBER.finditer(_normalize(obj)):
            yield float(m.group())


def _normalize(text):
    for bad, good in _MINUS.items():
        text = text.replace(bad, good)
    return text.replace(",", "")


def _variants(v):
    """36.9 → {"36.9", "37"} — 모델이 반올림해 쓰는 것까지 허용한다."""
    out = {f"{v:g}", f"{abs(v):g}"}
    for x in (v, abs(v)):
        out.add(f"{x:.1f}".rstrip("0").rstrip("."))
        out.add(str(int(round(x))))
    return out


def allowed_numbers(facts):
    allowed = set()
    for v in _walk_numbers(facts):
        allowed |= _variants(v)
    return allowed


def verify(text, facts):
    """
    사실표에 없는 숫자를 골라낸다.

    통과했다고 문장이 참인 것은 아니다. '지어낸 수치'라는 가장 큰 사고를
    막는 장치이며, 걸린 항목은 응답에 그대로 실어 사람이 판단하게 한다.
    """
    allowed = allowed_numbers(facts)
    unknown = []
    for m in _NUMBER.finditer(_normalize(text)):
        raw = m.group()
        value = float(raw)
        if abs(value) <= _SAFE_MAX and float(value).is_integer():
            continue                      # "3분의 1", "2개 동", 시각 등
        if raw.lstrip("-") in allowed or f"{value:g}" in allowed:
            continue
        unknown.append(raw)
    return sorted(set(unknown), key=unknown.index)
