"""
Claude로 ChatGPT용 프롬프트를 검토·개선 (Anthropic API, 사용량만큼 과금).

스케치·레퍼런스 이미지를 직접 보고:
 - 스케치 구조(단계 수, 배치, 시점, 대지 등)를 읽어 프롬프트에 구체적으로 반영
 - 레퍼런스 그래픽 언어(색 hex, 선, 라벨, 화살표, 첨경)를 추출
 - 입력끼리 충돌(색 규칙, 요소 추가 등)·모호한 표현을 찾아 고친 '개선 프롬프트'를 돌려준다.
"""

import base64
import io
import json

from PIL import Image

MODELS = {
    "Opus 5.5 (가장 꼼꼼)": "claude-opus-5-5",
    "Sonnet 5.5 (균형)": "claude-sonnet-5-5",
    "Haiku 5.5 (빠르고 저렴)": "claude-haiku-5-5",
}
# Opus 5.5 / Sonnet 5.5는 안전 분류기에 걸리면 다른 모델로 자동 재시도 (서버 측 fallback)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

SYSTEM = """You are a senior architectural-diagram art director and an expert prompt engineer for image-generation chatbots (ChatGPT).
You receive a DRAFT prompt that an app will paste into ChatGPT, plus the actual images that will be attached:
IMAGE "SKETCH" = the content to draw; images "REF n" = style references only.

Review the draft against the images and the user's intent, then rewrite it so ChatGPT produces exactly what the user wants.
Check in particular:
1. Sketch reading: describe concretely what must be preserved (number of steps/panels, their order and layout, viewpoint/projection, site boundary, key masses, voids/courtyards, arrows, text). Put these as explicit constraints in the prompt.
2. Reference style: extract the concrete graphic language (accent colors as hex, line weights, fills, label typography and layout, arrow types, tree/people style, background, what elements are ABSENT such as titles or legends). Put it into the prompt as precise rules.
3. Conflicts: contradictions between the diagram goal, keywords, mood text, style strength and the references (e.g. color meaning inconsistencies, elements the reference never uses). Resolve them following the draft's stated priorities.
4. Vague or redundant wording; anything ChatGPT is likely to misread.
5. Project facts: if MY DESIGN DRAWINGS and/or program text are given, extract the facts (program and space names, numbers, areas, floor counts, labels, design logic), state the ones the diagram needs, and remove anything that contradicts them or is not supported by them.
Rules for the improved prompt:
- Keep the draft's language (English draft -> English prompt). Keep the user's Korean quotes as quotes.
- Keep the attachment description consistent with how images are attached (separate files or one labeled board), the missing-image guard lines, and the instruction to reply in Korean.
- Be specific and compact (under ~2,500 characters). Do not invent design content the user did not give.
Write all explanations for the user (summary, issues, sketch reading) in Korean."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary_ko": {"type": "string"},
        "sketch_reading_ko": {"type": "string"},
        "reference_style_ko": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "problem_ko": {"type": "string"},
                    "fix_ko": {"type": "string"},
                },
                "required": ["severity", "problem_ko", "fix_ko"],
                "additionalProperties": False,
            },
        },
        "improved_prompt": {"type": "string"},
    },
    "required": ["summary_ko", "sketch_reading_ko", "reference_style_ko", "issues", "improved_prompt"],
    "additionalProperties": False,
}


def _image_block(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((1568, 1568))  # Claude 권장 최대 변 길이
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def review(api_key: str, model: str, effort: str, draft: str, context_ko: str,
           sketch: bytes, refs: list[bytes], projects: list[bytes] | None = None,
           extras: list[tuple[bytes, str]] | None = None) -> dict:
    """반환: SCHEMA 형태의 dict (+ 'model_used'). 실패 시 RuntimeError(한국어 메시지)."""
    import anthropic  # 필요할 때만 불러와서 앱 시작을 빠르게
    content: list[dict] = [{"type": "text", "text": "SKETCH (content to draw):"}, _image_block(sketch)]
    for i, b in enumerate(refs, 1):
        content += [{"type": "text", "text": f"REF {i} (style only):"}, _image_block(b)]
    for i, b in enumerate(projects or [], 1):
        content += [{"type": "text", "text": f"MY DESIGN DRAWING {i} (content facts, not style):"}, _image_block(b)]
    for b, label in extras or []:
        content += [{"type": "text", "text": f"{label}:"}, _image_block(b)]
    content.append({"type": "text", "text": f"USER SETTINGS (Korean):\n{context_ko}\n\nDRAFT PROMPT:\n<<<\n{draft}\n>>>"})

    params = dict(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    client = anthropic.Anthropic(api_key=api_key)
    try:
        if model in FALLBACK_MODELS:
            response = client.beta.messages.create(
                **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise RuntimeError("Claude API 키가 올바르지 않아요.") from None
    except anthropic.PermissionDeniedError:
        raise RuntimeError("이 키로는 해당 모델을 쓸 수 없어요 (권한/결제 확인).") from None
    except anthropic.NotFoundError:
        raise RuntimeError(f"모델을 찾지 못했어요: {model}") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Claude 사용 한도에 걸렸어요. 잠시 후 다시 시도하세요.") from None
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise RuntimeError("Claude 서버가 일시적으로 불안정해요. 잠시 후 다시 시도하세요.") from None
        raise RuntimeError(f"Claude 요청 오류: {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Claude 서버에 연결하지 못했어요 (인터넷 확인).") from None

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude가 이 요청 검토를 거절했어요. 입력 내용을 확인해 주세요.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("검토 결과가 너무 길어 잘렸어요. 검토 깊이를 낮춰 다시 시도하세요.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("Claude 응답을 해석하지 못했어요. 다시 시도해 주세요.") from None
    result["model_used"] = response.model
    return result


QA_SYSTEM = ("You are QA-checking an AI-generated architectural diagram before it is used in a presentation.\n"
             "Images: RESULT (to check), SKETCH (original content), REF n (style references).\n")
QA_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "issues_ko": {"type": "string"},
        "revision_prompt": {"type": "string"},
    },
    "required": ["verdict", "issues_ko", "revision_prompt"],
    "additionalProperties": False,
}


def qa(api_key: str, model: str, effort: str, result_png: bytes, sketch: bytes, refs: list[bytes],
       context_ko: str, prompt_used: str, projects: list[bytes] | None = None,
       extras: list[tuple[bytes, str]] | None = None) -> dict:
    """생성 결과 검수 (API). 반환: {"verdict": "pass"|"revise", "issues_ko", "revision_prompt"}"""
    import anthropic

    import prompts

    content: list[dict] = [{"type": "text", "text": "RESULT (to check):"}, _image_block(result_png),
                           {"type": "text", "text": "SKETCH:"}, _image_block(sketch)]
    for i, b in enumerate(refs, 1):
        content += [{"type": "text", "text": f"REF {i}:"}, _image_block(b)]
    for i, b in enumerate(projects or [], 1):
        content += [{"type": "text", "text": f"MY DESIGN DRAWING {i} (content facts):"}, _image_block(b)]
    for b, label in extras or []:
        content += [{"type": "text", "text": f"{label}:"}, _image_block(b)]
    content.append({"type": "text", "text": (
        f"{prompts.QA_CRITERIA}\n\nWrite issues_ko in Korean (numbered list, or '문제 없음'). If verdict is revise, "
        "revision_prompt is a concise English instruction for an image model that will EDIT the result image: start "
        "with 'Revise the attached diagram.', list concrete fixes, end with 'Keep everything else unchanged.' "
        "Otherwise revision_prompt is an empty string.\n\n"
        f"USER SETTINGS:\n{context_ko}\n\nPROMPT THAT WAS USED:\n{prompt_used}")})
    params = dict(model=model, max_tokens=16000, system=QA_SYSTEM,
                  output_config={"effort": effort, "format": {"type": "json_schema", "schema": QA_SCHEMA}},
                  messages=[{"role": "user", "content": content}])
    client = anthropic.Anthropic(api_key=api_key)
    try:
        if model in FALLBACK_MODELS:
            response = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default")
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise RuntimeError("Claude API 키가 올바르지 않아요.") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Claude 사용 한도에 걸렸어요. 잠시 후 다시 시도하세요.") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude 요청 오류: {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Claude 서버에 연결하지 못했어요 (인터넷 확인).") from None
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude가 이 검수 요청을 거절했어요.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("Claude 검수 응답을 해석하지 못했어요.") from None
    if data["verdict"] == "revise" and not data["revision_prompt"].strip():
        data["verdict"] = "pass_with_notes"
    return data
