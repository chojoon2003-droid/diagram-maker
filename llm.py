"""
분석/추천용 언어 모델 연결 (Gemini 무료 등급 우선, 없으면 OpenAI API).
이미지 '생성'은 여기서 하지 않는다 — 키워드 추천, 레퍼런스 스타일 분석만 담당.
"""

import base64
import io
import json
import re
import time

from PIL import Image


def _png(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((1536, 1536))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_EXCLUDE = ("image", "tts", "audio", "live", "embedding", "exp", "native", "computer", "robotics", "learnlm", "gemma")


def list_gemini_models(key: str) -> list[str]:
    """이 키로 generateContent를 쓸 수 있는 Gemini 텍스트/비전 모델 이름들."""
    from google import genai

    client = genai.Client(api_key=key)  # 참조 유지 (임시 객체면 목록 순회 중 연결이 닫힘)
    out = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        name = (m.name or "").removeprefix("models/")
        if "generateContent" in actions and name.startswith("gemini") and not any(x in name for x in _EXCLUDE):
            out.append(name)
    return sorted(set(out))


def pick_gemini_model(models: list[str], lite: bool) -> str:
    """최신 버전의 정식(비-preview) Flash 모델 우선. lite=True면 Flash-Lite 우선."""
    def ver(n: str) -> float:
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0

    cands = [n for n in models if "flash" in n and (("lite" in n) == lite)] or [n for n in models if "flash" in n] or models
    stable = [n for n in cands if "preview" not in n] or cands
    return max(stable, key=lambda n: (ver(n), -len(n)))


RETRYABLE = (429, 500, 503, 504)  # 한도 초과·서버 혼잡 → 잠시 후 재시도 / 다른 모델로


def rank_gemini_models(models: list[str], lite: bool) -> list[str]:
    """대체 순서: 선호 모델 → 같은 계열 다른 버전 → 나머지 Flash."""
    first = pick_gemini_model(models, lite)
    rest = [m for m in models if m != first and "flash" in m]
    rest.sort(key=lambda n: (("lite" in n) != lite, "preview" in n, -len(n)))
    return [first] + rest[:3]


def ask(prompt: str, images: list[bytes], *, json_mode: bool, gemini_key: str = "",
        gemini_model: str = "", gemini_fallbacks: tuple[str, ...] = (), openai_key: str = "",
        openai_model: str = "", on_fallback=None) -> str:
    if gemini_key:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        parts = [types.Part.from_bytes(data=_png(b), mime_type="image/png") for b in images] + [prompt]
        cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
        from google.genai import errors

        models = [gemini_model] + [m for m in gemini_fallbacks if m != gemini_model]
        last: Exception | None = None
        for i, model in enumerate(models):
            for attempt in range(2 if i == 0 else 1):  # 첫 모델은 한 번 더 재시도
                try:
                    r = client.models.generate_content(model=model, contents=parts, config=cfg)
                    if i and on_fallback:
                        on_fallback(model)
                    return r.text
                except errors.APIError as e:
                    if e.code not in RETRYABLE:
                        raise
                    last = e
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(friendly_error(last)) from last
    if openai_key:
        from openai import OpenAI

        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + base64.b64encode(_png(b)).decode()}}
            for b in images
        ]
        r = OpenAI(api_key=openai_key).chat.completions.create(
            model=openai_model,
            messages=[{"role": "user", "content": content}],
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        )
        return r.choices[0].message.content
    raise RuntimeError("Gemini 키나 OpenAI API 키가 필요해요.")


def friendly_error(e: Exception | None) -> str:
    code = getattr(e, "code", None)
    if code == 503 or code == 500 or code == 504:
        return "구글 Gemini 서버가 지금 붐벼요 (다른 모델로도 시도했어요). 1~2분 뒤 다시 눌러주세요."
    if code == 429:
        return "Gemini 무료 사용 한도에 걸렸어요. 1분 정도 기다렸다가 다시 시도하세요. (하루 한도면 내일 풀려요)"
    return str(e)[:200]


PHRASE_PROMPT = """사용자가 만들고 싶은 건축 다이어그램의 분위기를 문장으로 적었다.
다이어그램 종류: "{goal}"
사용자 문장: "{text}"

문장을 의미 단위 구절로 나누고, 각 구절마다 두 종류의 키워드를 추천해라.
1) direct: 그 구절을 그대로 '대체'할 그래픽 표현 키워드 (선, 색, 질감, 투상법, 주석, 첨경, 구도). 딱 맞는 게 없으면 빈 배열.
2) similar: 그 구절과 '비슷한 느낌'을 주는 건축적 언어 4~6개 — 공간, 빛, 재료, 매스, 비례, 리듬, 경계, 시퀀스 같은
   건축가가 쓰는 표현 (예: "고요한" → 절제된 여백, 수평적 연속성, 확산광, 깊은 처마 그림자). similar는 절대 비우지 말 것.
- ko: 2~10자 한국어, en: 이미지 생성 프롬프트에 바로 쓸 영어 표현.
JSON으로만 답해라:
{{"phrases":[{{"phrase":"원문 구절","direct":[{{"ko":"...","en":"..."}}],"similar":[{{"ko":"...","en":"..."}}]}}]}}"""


def _labels(items) -> list[str]:
    return [f"{k['ko']} · {k['en']}" for k in items or [] if isinstance(k, dict) and k.get("ko") and k.get("en")]


def phrase_keywords(text: str, goal: str, **keys) -> list[tuple[str, list[str], list[str]]]:
    """[(구절, 직접 대체 키워드, 비슷한 느낌의 건축 언어)]"""
    raw = ask(PHRASE_PROMPT.format(text=text, goal=goal or "미정"), [], json_mode=True, **keys)
    data = json.loads(raw)
    return [(it.get("phrase", ""), _labels(it.get("direct")), _labels(it.get("similar") or it.get("keywords")))
            for it in data.get("phrases", [])]


STYLE_PROMPT = """너는 건축 다이어그램 아트디렉터다. 첨부된 레퍼런스 다이어그램들과 사용자가 적은 느낌을 바탕으로
'그래픽 스타일'만 정리해서 이미지 생성 모델이 그대로 따라 할 수 있는 스타일 가이드를 영어로 작성해라.
레퍼런스의 내용(건물 형태)은 무시한다. 다음 항목을 짧은 bullet로:
- Projection / view
- Line work (weight hierarchy, color, hand-drawn vs vector, hatching)
- Color palette (hex 추정치 포함, 강조색 규칙)
- Fill & texture
- Annotation (font, leader lines, arrows, numbering)
- Entourage (people, trees: style & density)
- Background & composition
- Overall mood keywords (5 words)

사용자 입력:
{user}"""


def style_guide(images: list[bytes], user_text: str, **keys) -> str:
    return ask(STYLE_PROMPT.format(user=user_text or "(없음)"), images, json_mode=False, **keys)
