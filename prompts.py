"""
ChatGPT / 이미지 모델에 보낼 프롬프트 (영어 기본, 한국어 선택).
사용자가 한국어로 쓴 설명·느낌은 그대로 넣고 '(user's words, Korean)'으로 표시한다.
"""

from dataclasses import dataclass, field

TYPE_EN = {
    "매스 형성 과정": "massing process", "프로그램 조닝": "program zoning", "동선": "circulation",
    "분해 액소": "exploded axonometric", "환경 (빛·바람)": "environmental (light & wind)",
    "단면 다이어그램": "sectional diagram", "배치·맥락": "site & context", "구조·재료": "structure & materials",
    "컨셉 다이어그램": "concept diagram", "단계별 시퀀스": "step-by-step sequence",
}
QUALITY_EN = {
    "초안 (빠름)": "Quick rough draft quality (minimal detail).",
    "표준": "Standard presentation quality.",
    "고화질": "Highest quality: maximum resolution, crisp lines and legible text, rich texture and detail.",
}
QUALITY_KO = {
    "초안 (빠름)": "빠르게 확인할 러프 초안 수준으로 (디테일 최소).",
    "표준": "발표용 표준 품질로.",
    "고화질": "최고 품질로: 가능한 최대 해상도, 선과 글자를 선명하게, 질감과 디테일을 충실하게.",
}
ASPECT_EN = {"자동": "", "가로 (3:2)": "landscape 3:2", "세로 (2:3)": "portrait 2:3", "정사각형": "square 1:1"}
THINK_EN = {
    "자동": "",
    "빠르게": "Be quick: skip the style summary and go straight to the image.",
    "깊게 생각": "Think carefully first: study the sketch's geometry, hierarchy and the references' graphic rules "
                 "in detail before generating, then double-check the result against the sketch.",
}
THINK_KO = {
    "자동": "",
    "빠르게": "빠르게: 스타일 요약은 건너뛰고 바로 이미지를 만들어줘.",
    "깊게 생각": "깊게 생각해줘: 생성 전에 스케치의 형태·위계와 레퍼런스의 그래픽 규칙을 자세히 분석하고, "
                 "생성 후 스케치와 비교해 다시 점검해줘.",
}


def ref_names(n: int) -> str:
    return ", ".join(f"2_reference_{i}.png" for i in range(1, n + 1))


def en(label: str) -> str:
    return label.split(" · ")[-1]


def ko(label: str) -> str:
    return label.split(" · ")[0]


@dataclass
class Spec:
    types: list[str] = field(default_factory=list)
    goal: str = ""
    mood: str = ""
    keywords: list[str] = field(default_factory=list)  # "한국어 · english"
    style_guide: str = ""
    strict: bool = True
    quality: str = "표준"
    aspect: str = "가로 (3:2)"
    think: str = "자동"
    extra: str = ""
    style_strength: str = "균형"  # 구조 우선 / 균형 / 스타일 우선


STRENGTH_EN = {
    "구조 우선": "Use the references only as loose inspiration; clarity of the content comes first.",
    "균형": "Match the references' graphic language closely: accent color(s), line weights, fills, label typography, "
            "arrow types and tree/people style.",
    "스타일 우선": "Use ONLY the references' graphic language: the same accent color(s) and palette, line weights, fills, "
                  "label typography and layout, arrow types, tree/people style and background. Do NOT add elements the "
                  "references do not use (e.g. big title blocks, legends, key-diagram strips, extra annotations) unless I "
                  "explicitly asked for them. Content and geometry still follow the sketch.",
}
STRENGTH_KO = {
    "구조 우선": "레퍼런스는 느슨한 참고만. 내용 전달이 우선.",
    "균형": "레퍼런스의 그래픽 언어(강조색, 선 굵기, 채색, 라벨 서체, 화살표, 나무·사람 표현)를 가깝게 따를 것.",
    "스타일 우선": "레퍼런스의 그래픽 언어만 사용: 같은 강조색·팔레트, 선 굵기, 채색, 라벨 서체와 배치, 화살표, 나무·사람, 배경. "
                  "레퍼런스에 없는 요소(큰 제목, 범례, 키 다이어그램 띠, 추가 주석)는 내가 요청하지 않았다면 넣지 말 것. "
                  "내용과 형태는 스케치를 따른다.",
}


def ref_guard_en(n_refs: int, board: bool) -> str:
    if board:
        return ("Check first: the board must contain at least one 'REF' panel. If it does not, do not generate — "
                "ask me to attach the style reference.")
    if n_refs:
        return (f"Check first: I am attaching 1 sketch + {n_refs} style reference image(s). If any reference image is "
                "missing, do not generate — ask me to attach it.")
    return ""


def ref_guard_ko(n_refs: int, board: bool) -> str:
    if board:
        return "먼저 확인: 보드에 'REF' 칸이 하나 이상 있어야 해. 없으면 생성하지 말고 레퍼런스를 첨부해 달라고 해줘."
    if n_refs:
        return (f"먼저 확인: 스케치 1장 + 스타일 레퍼런스 {n_refs}장을 첨부해. 레퍼런스가 빠졌으면 생성하지 말고 "
                "첨부해 달라고 해줘.")
    return ""


# ---------------------------------------------------------------- 공통 블록 (영어)
def goal_en(s: Spec) -> str:
    lines = []
    if s.types:
        lines.append("- Type: " + ", ".join(TYPE_EN.get(t, t) for t in s.types))
    if s.goal:
        lines.append(f"- Description (user's words, Korean): {s.goal}")
    return "\n".join(lines) or "- Not specified: infer the intent from the sketch."


def style_header_en(s: Spec) -> str:
    if s.style_strength == "스타일 우선":
        return "PRIORITY 3 — graphic style (follow STRICTLY; it may override how the goal is drawn, never the geometry):"
    return "PRIORITY 3 — graphic style (apply only where it does not conflict with 1–2):"


def structure_en(s: Spec) -> str:
    if s.strict:
        return ("STRICTLY keep the sketch's massing, proportions, positions, viewpoint, arrows and text content. "
                "Do not add or remove building elements.")
    return "Keep the sketch's layout and intent, but you may straighten lines and tidy proportions."


def style_en(s: Spec) -> str:
    lines = [f"- Reference strength ({s.style_strength}): {STRENGTH_EN[s.style_strength]}"]
    if s.keywords:
        lines.append("- Style keywords: " + ", ".join(en(k) for k in s.keywords))
    if s.mood:
        lines.append(f"- Desired feel (user's words, Korean): {s.mood}")
    if s.style_guide:
        lines.append("- Style guide:\n" + s.style_guide)
    return "\n".join(lines)


# ---------------------------------------------------------------- ChatGPT (영어)
def chatgpt_en(s: Spec, n_refs: int, board: bool) -> str:
    if board:
        images = ("ONE attached board image: the LEFT panel labeled 'SKETCH = CONTENT' is what to draw; "
                  "the RIGHT panels labeled 'REF n = STYLE ONLY' are style references. "
                  "Output ONLY the redrawn sketch as a new image (not the board, no labels from the board).")
    elif n_refs:
        images = ("- 1_sketch.png = CONTENT to draw (rough hand sketch or 3D model screenshot)\n"
                  f"- {ref_names(n_refs)} = STYLE references only — never copy their buildings or content")
    else:
        images = "- 1_sketch.png = CONTENT to draw (rough hand sketch or 3D model screenshot). No reference images."
    aspect = f" Aspect ratio: {ASPECT_EN[s.aspect]}." if ASPECT_EN.get(s.aspect) else ""
    think = f"\n{THINK_EN[s.think]}" if THINK_EN.get(s.think) else ""
    steps = (
        "1) Generate the diagram image."
        if s.think == "빠르게" or not (n_refs or board)
        else "1) First summarize the references' graphic style in ≤5 bullets "
             "(projection, line-weight hierarchy, palette with hex, texture, annotation, entourage).\n"
             "2) Then generate the diagram image in that style."
    )
    return f"""Create a presentation-ready ARCHITECTURAL DIAGRAM from the attached image(s).
If the images are not attached yet, reply only "이미지를 첨부해 주세요" and wait for my next message with the images.
{ref_guard_en(n_refs, board)}

ATTACHED
{images}

PRIORITY 1 — what the diagram must communicate (overrides style):
{goal_en(s)}

PRIORITY 2 — structure:
{structure_en(s)}

{style_header_en(s)}
{style_en(s)}

STEPS
{steps}
{QUALITY_EN[s.quality]}{aspect}{think}
{f"Extra instruction: {s.extra}" if s.extra else ""}

For my later revision requests: keep everything from the previous image unchanged except what I ask to change.
Keep any text labels exactly as written in the sketch. Write your text replies to me in Korean."""


# ---------------------------------------------------------------- ChatGPT (한국어)
def chatgpt_ko(s: Spec, n_refs: int, board: bool) -> str:
    if board:
        images = ("첨부한 보드 이미지 한 장: 왼쪽 'SKETCH = CONTENT' 칸이 그릴 내용, 오른쪽 'REF n = STYLE ONLY' 칸들은 "
                  "스타일 레퍼런스. 결과는 보드가 아니라 스케치를 다시 그린 이미지 한 장만.")
    elif n_refs:
        images = (f"- 1_sketch.png = 그릴 내용 (손스케치 / 3D 캡처)\n"
                  f"- {ref_names(n_refs)} = 스타일 레퍼런스 (형태는 절대 복사하지 말 것)")
    else:
        images = "- 1_sketch.png = 그릴 내용 (손스케치 / 3D 캡처). 레퍼런스 이미지는 없음."
    goal = "\n".join(x for x in [
        f"- 유형: {', '.join(s.types)}" if s.types else "",
        f"- 설명: {s.goal}" if s.goal else "",
    ] if x) or "- 스케치를 보고 판단"
    style = "\n".join(x for x in [
        f"- 레퍼런스 강도({s.style_strength}): {STRENGTH_KO[s.style_strength]}",
        f"- 스타일 키워드: {', '.join(s.keywords)}" if s.keywords else "",
        f"- 원하는 느낌: {s.mood}" if s.mood else "",
        f"- 스타일 가이드:\n{s.style_guide}" if s.style_guide else "",
    ] if x) or "- 레퍼런스 이미지의 그래픽 스타일을 따를 것"
    rule = ("스케치의 매스, 비율, 배치, 시점, 화살표, 글자 내용을 그대로 유지. 건물 요소를 추가하거나 빼지 말 것."
            if s.strict else "스케치의 배치와 의도는 유지하되 선을 정돈하고 비율을 다듬어도 됨.")
    ratio = f" 비율은 {s.aspect}." if s.aspect != "자동" else ""
    steps = ("1) 바로 다이어그램 이미지를 생성해줘." if s.think == "빠르게" or not (n_refs or board) else
             "1) 레퍼런스의 그래픽 스타일(투상법, 선 위계, 색상 hex, 질감, 주석, 첨경)을 5줄 이내로 먼저 정리해줘.\n"
             "2) 그 스타일로 다이어그램 이미지를 생성해줘.")
    return f"""첨부 이미지로 발표용 건축 다이어그램을 만들어줘.
아직 이미지가 첨부되지 않았다면 "이미지를 첨부해 주세요"라고만 답하고 다음 메시지를 기다려줘.
{ref_guard_ko(n_refs, board)}

[첨부]
{images}

[1순위 · 어떤 다이어그램인지 — 스타일보다 우선]
{goal}

[2순위 · 구조] {rule}

[3순위 · 스타일 — {"엄격히 따를 것 (형태는 스케치 유지)" if s.style_strength == "스타일 우선" else "1, 2순위와 충돌하지 않는 범위에서"}]
{style}

[진행]
{steps}
{QUALITY_KO[s.quality]}{ratio} {THINK_KO.get(s.think, "")}
{f"추가 지시: {s.extra}" if s.extra else ""}

이후 수정 요청을 하면, 요청한 부분 외에는 직전 이미지를 그대로 유지해서 다시 생성해줘."""


# ---------------------------------------------------------------- API 이미지 모델 (영어)
def image_api(s: Spec, has_refs: bool, task: str) -> str:
    refs = ("IMAGE 2+ = style references ONLY. Never copy their buildings or content."
            if has_refs else "No reference images; follow the style text.")
    return f"""You are making an architectural diagram.
IMAGE 1 = the content to draw (rough sketch, 3D model screenshot, or a previous version).
{refs}

PRIORITY 1 — what this diagram must communicate (overrides style):
{goal_en(s)}

PRIORITY 2 — structure:
{structure_en(s)}

{style_header_en(s)}
{style_en(s)}

Task: {task}
{QUALITY_EN[s.quality]} Keep any text labels exactly as in the sketch."""


# ---------------------------------------------------------------- Claude(구독)에게 보낼 검토 요청
def claude_review_request(draft: str, context_ko: str, n_refs: int, board: bool) -> str:
    if board:
        att = "ONE board image: left panel 'SKETCH' = content to draw, right panels 'REF n' = style references."
    else:
        att = f"Image 1 = SKETCH (content to draw)" + (f", images 2–{n_refs + 1} = style REFERENCES." if n_refs else ". No references.")
    return f"""Act as a senior architectural-diagram art director and prompt engineer.
I will paste the images right after this message. If they are not attached yet, reply only "이미지를 첨부해 주세요" and wait.
Attached: {att}

Review the DRAFT prompt below (it will be pasted into ChatGPT together with the same images) and improve it:
1. Read the sketch: list what must be preserved (number/order/layout of steps, viewpoint, site boundary, key masses, voids/courtyards, arrows, text) and add them as explicit constraints.
2. Read the references: extract the concrete graphic language (accent colors as hex, line weights, fills, label typography/layout, arrow types, tree/people style, background, and elements they do NOT use such as titles or legends) and add precise rules.
3. Fix conflicts between the goal, keywords, mood, style strength and references; remove vague or redundant wording.
Keep the draft's language, its attachment description, its missing-image guard lines and the "reply in Korean" line. Keep it under ~2,500 characters. Do not invent design content.

Answer in Korean: first a short list of the problems you found (most important first), then the improved prompt inside ONE code block (```) so I can copy it.

USER SETTINGS:
{context_ko}

DRAFT PROMPT:
{draft}"""


# ---------------------------------------------------------------- Claude Code(구독, CLI)용 검토 요청
MARK_START, MARK_END = "=== IMPROVED PROMPT START ===", "=== IMPROVED PROMPT END ==="


def claude_cli_request(draft: str, context_ko: str, sketch: str, refs: list[str]) -> str:
    files = f"- {sketch} = SKETCH (content to draw)\n" + "".join(f"- {r} = REFERENCE {i} (style only)\n"
                                                              for i, r in enumerate(refs, 1))
    return f"""Act as a senior architectural-diagram art director and prompt engineer.
The images are files in the current directory. Use the Read tool to look at EVERY one of them before reviewing:
{files}
Review the DRAFT prompt below. It will be sent to ChatGPT/Codex (image generation) together with the same image files.
1. Read the sketch: list what must be preserved (number/order/layout of steps, viewpoint, site boundary, key masses, voids/courtyards, arrows, text) and add them as explicit constraints.
2. Read the references: extract the concrete graphic language (accent colors as hex, line weights, fills, label typography/layout, arrow types, tree/people style, background, and elements they do NOT use such as titles or legends) and add precise rules.
3. Fix conflicts between the goal, keywords, mood, style strength and references; remove vague or redundant wording.
Keep the draft's language, its attachment description (file names), and the "reply in Korean" line. Keep it under ~2,500 characters. Do not invent design content. Do not edit or create any files.

OUTPUT FORMAT (exactly):
First, in Korean, a short numbered list of the problems you found and how you fixed them (most important first).
Then the improved prompt between these two marker lines, with nothing else between them:
{MARK_START}
...improved prompt...
{MARK_END}

USER SETTINGS:
{context_ko}

DRAFT PROMPT:
{draft}"""


# ---------------------------------------------------------------- 결과 이미지 검수 (Claude)
REV_START, REV_END = "=== REVISION PROMPT START ===", "=== REVISION PROMPT END ==="
QA_CRITERIA = """Check the GENERATED result against:
1. Structure: does it preserve the sketch (number/order/layout of steps, viewpoint, identical site boundary, key masses, voids/courtyards, arrows, text)?
2. Goal: does it communicate the diagram goal in the user settings?
3. Style: does it follow the references' graphic language (accent colors, line weights, fills, labels, arrows, entourage) and avoid elements the references do not use (titles, legends, extra strips) when the style strength asks for that?
4. Quality: garbled or misspelled text, broken geometry, artifacts, missing or duplicated parts, inconsistent color meaning.
Only flag problems that clearly matter for a presentation diagram. If it is good enough, PASS."""


def qa_request_cli(result: str, sketch: str, refs: list[str], context_ko: str, prompt_used: str) -> str:
    files = (f"- {result} = GENERATED RESULT (to check)\n- {sketch} = original SKETCH\n"
             + "".join(f"- {r} = STYLE REFERENCE {i}\n" for i, r in enumerate(refs, 1)))
    return f"""You are QA-checking an AI-generated architectural diagram before it is used in a presentation.
The images are files in the current directory. Use the Read tool to look at EVERY one of them:
{files}
{QA_CRITERIA}

OUTPUT FORMAT (exactly):
Line 1: VERDICT: PASS   or   VERDICT: REVISE
Then, in Korean, a short numbered list of the problems found (most important first), or "문제 없음".
If REVISE, then a concise English revision instruction for an image model that will EDIT the generated result image
(it will receive the result, the sketch and the references). Start with "Revise the attached diagram {result}." list the
concrete fixes, and end with "Keep everything else unchanged." Put it between these marker lines:
{REV_START}
...revision instruction...
{REV_END}
Do not edit or create any files.

USER SETTINGS:
{context_ko}

PROMPT THAT WAS USED TO GENERATE IT:
{prompt_used}"""
