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
    # 평면 리터칭
    "실별 색 구분": "room/zone color coding", "가구·인테리어": "furniture & interior layout",
    "조경·외부공간": "landscape & outdoor spaces", "바닥 재질": "floor materials", "그림자·깊이감": "shadows & depth",
    "흑백 포셰 강조": "black-and-white poché emphasis", "동선 표시": "circulation paths",
    # 단면 리터칭
    "절단면 포셰 강조": "solid poché of cut elements", "지반·지형": "ground & terrain", "빛·환경 흐름": "light & environmental flows",
    "사람·스케일": "people & scale", "단면 투시(깊이감)": "section perspective depth", "재료·구조": "materials & structure",
    "배경·하늘": "background & sky",
    # 렌더링
    "주간 (맑음)": "clear daylight", "골든아워": "golden hour, warm low sun", "야경": "night view with interior glow",
    "흐림·비": "overcast / light rain mood", "계절감": "seasonal atmosphere", "눈높이 컷": "eye-level shot",
    "조감 컷": "aerial / bird's-eye shot", "디테일 컷": "close-up detail shot", "첨경 많이": "lively, many people",
    "첨경 적게": "calm, few people",
}
QUALITY_EN = {
    "초안 (빠름)": "Quick rough draft quality (minimal detail).",
    "표준": "Standard presentation quality.",
    "고화질": "Highest quality: maximum resolution, crisp lines and legible text (resolution, not extra detail).",
}
QUALITY_KO = {
    "초안 (빠름)": "빠르게 확인할 러프 초안 수준으로 (디테일 최소).",
    "표준": "발표용 표준 품질로.",
    "고화질": "최고 품질로: 가능한 최대 해상도, 선과 글자를 선명하게 (해상도를 높이라는 뜻이지 디테일을 더하라는 뜻은 아님).",
}
ASPECT_EN = {"자동": "", "가로 (3:2)": "landscape 3:2", "세로 (2:3)": "portrait 2:3", "정사각형": "square 1:1"}
THINK_EN = {
    "자동": "",
    "빠르게": "Draw directly.",
    "깊게 생각": "Before drawing, read the inputs carefully (structure, facts, style rules), then draw once.",
}
THINK_KO = {
    "자동": "",
    "빠르게": "바로 그려줘.",
    "깊게 생각": "그리기 전에 입력(구조·사실·스타일 규칙)을 꼼꼼히 읽고, 한 번에 그려줘.",
}

# OpenAI 쪽은 '생성만': 자체 검토·재생성·설명으로 토큰을 쓰지 않게 (검수는 Claude가 따로 함)
EFFICIENCY_EN = ("WORK EFFICIENTLY: produce exactly ONE image in a single pass. Do not critique, verify, compare or "
                 "regenerate it yourself, do not make variants, and do not explain your process — a separate reviewer "
                 "checks the result. When done, reply with one short line in Korean.")
EFFICIENCY_KO = ("효율적으로: 이미지 한 장을 한 번에 만들어줘. 스스로 검토·비교·재생성하지 말고, 여러 안을 만들지 말고, "
                 "과정 설명도 하지 마 — 검수는 따로 해. 끝나면 한국어로 한 줄만 답해줘.")

# 첨경·디테일 수준 (사람 옷 재질 같은 과한 디테일 방지)
DETAIL_LEVELS = ["단순", "사실적 (과한 디테일 없이)", "풍부"]
DETAIL_EN = {
    "단순": "Detail level SIMPLE: entourage (people, trees, cars, furniture) as clean silhouettes or simple shapes; "
            "flat surfaces; no textures, faces or small ornaments.",
    "사실적 (과한 디테일 없이)": "Detail level REALISTIC BUT RESTRAINED: people, trees, cars and furniture look realistic in "
                         "proportion, pose and silhouette, but WITHOUT fine detail — no clothing fabric or textures, no "
                         "facial features, no logos, no leaf-by-leaf foliage, no tiny props. Put detail only where the "
                         "drawing's message needs it.",
    "풍부": "Detail level RICH: realistic entourage and material textures are welcome, but never let detail compete "
            "with the drawing's main message.",
}
DETAIL_KO = {
    "단순": "디테일 단순: 사람·나무·차·가구는 깔끔한 실루엣이나 단순한 형태로, 질감·얼굴·작은 장식 없이.",
    "사실적 (과한 디테일 없이)": "디테일 절제: 사람·나무·차·가구는 비례·자세·실루엣이 사실적이면 충분. 옷 재질·질감, 얼굴, 로고, "
                         "잎 하나하나, 작은 소품 같은 세부 묘사는 넣지 말 것. 디테일은 도면이 전달할 내용에만.",
    "풍부": "디테일 풍부: 사실적인 첨경과 재료 질감 허용. 단, 디테일이 주제를 가리지 않게.",
}


# ---------------------------------------------------------------- 작업 종류 · 형태 변형 단계
WORK_TYPES = ["다이어그램", "평면 리터칭", "단면 리터칭", "렌더링"]
WORK_EN = {
    "다이어그램": "ARCHITECTURAL DIAGRAM",
    "평면 리터칭": "FLOOR PLAN (a retouched rendering of my own drawing)",
    "단면 리터칭": "SECTION drawing (a retouched rendering of my own drawing)",
    "렌더링": "PHOTOREALISTIC ARCHITECTURAL RENDERING of my 3D model view",
}
WORK_KO = {"다이어그램": "발표용 건축 다이어그램", "평면 리터칭": "발표용 평면도 (내 도면 리터칭)",
           "단면 리터칭": "발표용 단면도 (내 도면 리터칭)", "렌더링": "실사 건축 렌더링 (내 3D 모델 뷰)"}
INPUT_EN = {
    "다이어그램": "CONTENT to draw (rough hand sketch or 3D model screenshot)",
    "평면 리터칭": "MY FLOOR PLAN DRAWING to retouch",
    "단면 리터칭": "MY SECTION DRAWING to retouch",
    "렌더링": "MY 3D MODEL VIEW to render (white/clay model capture — the geometry and camera are final)",
}
INPUT_KO = {"다이어그램": "그릴 내용 (손스케치 / 3D 캡처)", "평면 리터칭": "리터칭할 내 평면도",
            "단면 리터칭": "리터칭할 내 단면도", "렌더링": "렌더링할 내 3D 모델 뷰 (화이트/클레이 모델 캡처 — 형태와 카메라 확정)"}
DRAWING_RULES_EN = {
    "평면 리터칭": ("Treat it as an orthographic FLOOR PLAN: keep it strictly top-down (no perspective, no 3D), keep the "
                 "exact walls and wall thickness, doors and swings, windows, stairs, columns/grid, room names and areas. "
                 "Retouch only by rendering: poché of cut walls, room fills/zoning colors, floor materials, furniture and "
                 "landscape, soft shadows — as the style asks."),
    "단면 리터칭": ("Treat it as an orthographic SECTION: keep the view exactly (no perspective unless the drawing is "
                 "already a section perspective), keep floor levels, slab and wall thickness, the cut, openings, roof "
                 "profile, ground line and level marks. Retouch only by rendering: solid poché of cut elements, ground "
                 "hatch, lighter elements beyond, sky/background, people for scale, light — as the style asks."),
}
DRAWING_RULES_EN["렌더링"] = (
    "Treat it as a FINAL CAMERA VIEW: keep exactly the same viewpoint, focal length, perspective, horizon and framing. "
    "Keep the building geometry exactly: massing, edges, roof lines, floor lines, the number, size and pattern of "
    "windows, doors and mullions. Render photorealistic materials, lighting, sky, context and entourage on top. "
    "Do not add, remove or reshape any part of the building.")
DRAWING_RULES_KO = {
    "평면 리터칭": ("정사영 평면도로 취급: 위에서 본 그대로(투시·3D 금지), 벽과 벽 두께, 문과 문 열림, 창, 계단, 기둥·그리드, "
                 "실명·면적을 정확히 유지. 리터칭은 표현만: 절단 벽 포셰, 실별 색, 바닥 재질, 가구·조경, 부드러운 그림자."),
    "단면 리터칭": ("정사영 단면도로 취급: 보는 방향 그대로(원래 단면투시가 아니면 투시 금지), 층 레벨, 슬래브·벽 두께, 절단면, "
                 "개구부, 지붕선, 지반선, 레벨 표기를 유지. 리터칭은 표현만: 절단 부재 포셰, 지반 해치, 원경 요소는 옅게, "
                 "하늘·배경, 스케일용 사람, 빛."),
    "렌더링": ("확정된 카메라 뷰로 취급: 시점·화각·투시·지평선·프레이밍을 그대로. 건물 형태(매스, 모서리, 지붕선, 층 라인, "
             "창·문·멀리언의 개수·크기·패턴)를 그대로 두고 실사 재료·조명·하늘·주변·첨경만 입힐 것. 건물 부분 추가·삭제·변형 금지."),
}
FORM_LABELS = ["① 완전 고정", "② 선 정리", "③ 비율 다듬기", "④ 구성 정리", "⑤ 재해석"]
FORM_HELP = [
    "선·벽·매스·위치·비율·시점·글자를 그대로 두고 색·채움·질감·그림자·첨경만 입혀요.",
    "모든 요소와 위치·비율은 그대로, 삐뚤어진 선만 곧게 펴고 끊긴 선을 잇고 선 굵기를 통일해요.",
    "요소와 배치는 그대로, 어색하게 틀어진 비율·정렬만 살짝 바로잡아요. 요소 추가·삭제 없음.",
    "설계 의도와 요소 관계는 유지, 작은 디테일을 단순화하거나 합치고 간격·구도를 정리해요.",
    "개념·전체 배치·부분 개수·핵심 관계만 유지하고 형태는 더 명확하게 자유롭게 다시 그려요.",
]
FORM_EN = [
    "LOCK the geometry: every line, wall, opening, mass, position, proportion, viewpoint and text stays exactly where it "
    "is. Only add color, fills, texture, shading and entourage on top. Do not move, redraw, add or remove any element.",
    "Keep all elements, positions, proportions and the viewpoint exactly. You may only clean up the linework "
    "(straighten wobbly lines, close small gaps, unify line weights). Do not add or remove elements.",
    "Keep every element and the layout. You may slightly correct proportions and alignments that look unintentionally "
    "off, but do not add or remove elements or change the design.",
    "Keep the design intent, the elements and their relationships. You may simplify small details, merge tiny parts "
    "and adjust spacing/composition for clarity. Do not invent new design elements.",
    "Use the input as the concept: keep the overall layout, the number of parts and the key relationships, but you may "
    "freely redraw forms for a stronger, cleaner result. Do not change what it communicates.",
]
FORM_KO = [
    "형태 완전 고정: 모든 선·벽·개구부·매스·위치·비율·시점·글자를 그대로 두고, 색·채움·질감·그림자·첨경만 덧입힐 것. "
    "어떤 요소도 옮기거나 다시 그리거나 추가·삭제하지 말 것.",
    "모든 요소·위치·비율·시점은 그대로. 선만 정리(삐뚤어진 선 펴기, 작은 끊김 잇기, 선 굵기 통일). 요소 추가·삭제 금지.",
    "모든 요소와 배치는 유지. 의도치 않게 틀어진 비율·정렬만 살짝 바로잡을 것. 요소 추가·삭제나 설계 변경 금지.",
    "설계 의도·요소·관계는 유지. 작은 디테일 단순화·병합, 간격·구도 정리는 허용. 새로운 설계 요소를 지어내지 말 것.",
    "입력을 개념으로 사용: 전체 배치·부분 개수·핵심 관계만 유지하고 형태는 더 명확하게 자유롭게 다시 그려도 됨. "
    "전달하는 내용은 바꾸지 말 것.",
]


def project_names(n: int) -> str:
    return ", ".join(f"3_project_{i}.png" for i in range(1, n + 1))


def has_facts(s: "Spec") -> bool:
    return bool(s.project_text.strip() or s.n_project)


def facts_en(s: "Spec") -> str:
    if not has_facts(s):
        return ""
    lines = ["PROJECT FACTS — my own design documents; they are the source of truth for CONTENT:"]
    if s.n_project:
        lines.append(f"- {project_names(s.n_project)} = MY DESIGN DRAWINGS/DIAGRAMS of this project "
                     "(read content from them; do NOT copy their graphic style)")
    if s.project_text.strip():
        lines.append("- Program & design logic (user's words, Korean):\n" + s.project_text.strip()[:3000])
    if s.facts_strict:
        lines.append("- RULE: use only programs, space/zone names, numbers, areas, floor counts, labels and design moves "
                     "that appear in the sketch or these documents. Do NOT invent new programs, labels, numbers, "
                     "annotations or design moves. If something is unclear, leave it out instead of guessing.")
    else:
        lines.append("- Keep the content consistent with these documents; never contradict them.")
    return "\n".join(lines)


def facts_ko(s: "Spec") -> str:
    if not has_facts(s):
        return ""
    lines = ["[내 설계 자료 — 내용의 기준]"]
    if s.n_project:
        lines.append(f"- {project_names(s.n_project)} = 이 프로젝트의 내 설계 도면/다이어그램 (내용만 참고, 그래픽 스타일은 따라하지 말 것)")
    if s.project_text.strip():
        lines.append("- 프로그램·설계 논리:\n" + s.project_text.strip()[:3000])
    lines.append("- 규칙: 스케치나 설계 자료에 있는 프로그램·공간 이름·숫자·면적·층수·라벨·설계 행위만 사용. "
                 "없는 내용을 지어내지 말고, 불확실하면 빼줘." if s.facts_strict
                 else "- 이 자료와 내용이 어긋나지 않게 할 것.")
    return "\n".join(lines)


def render_en(s: "Spec") -> str:
    """렌더링 전용: 재료 지정·재료 색 코딩 맵·기준 컷 블록"""
    lines = []
    if s.materials.strip():
        lines.append("MATERIALS (apply exactly these; do not invent other materials):\n" + s.materials.strip()[:1500])
    if s.has_material_map:
        legend = "; ".join(f"{h} = {m}" for h, m in s.material_legend if m.strip()) or "(see colors)"
        lines.append("MATERIAL ID MAP: 4_material_map.png is the SAME camera view where each flat color marks one "
                     f"material. Apply each material exactly inside its color region: {legend}. "
                     "Do not render the flat colors themselves.")
    return "\n".join(lines)


def render_ko(s: "Spec") -> str:
    lines = []
    if s.materials.strip():
        lines.append("[재료 — 이것만 정확히 적용, 다른 재료 지어내지 말 것]\n" + s.materials.strip()[:1500])
    if s.has_material_map:
        legend = "; ".join(f"{h} = {m}" for h, m in s.material_legend if m.strip()) or "(색 참고)"
        lines.append("[재료 색 코딩 맵] 4_material_map.png는 같은 카메라 뷰에서 재료마다 단색으로 칠한 그림. "
                     f"각 색 영역에 해당 재료를 정확히 입힐 것: {legend}. 단색 자체를 그리지는 말 것.")
    return "\n".join(lines)


ANCHOR_EN = ("The LAST style reference is an APPROVED SHOT of this same project: match its materials, lighting, color "
             "grading, sky and entourage style exactly so the shots look like one set.")
ANCHOR_KO = "마지막 스타일 레퍼런스는 같은 프로젝트의 확정 컷: 재료·조명·색감·하늘·첨경 스타일을 똑같이 맞춰 한 세트처럼 보이게."


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
    detail: str = "사실적 (과한 디테일 없이)"  # DETAIL_LEVELS
    materials: str = ""  # 렌더링: 재료 지정 글 (예: 외벽: 노출콘크리트)
    material_legend: list = field(default_factory=list)  # 렌더링: [(hex, 재료)] 재료 색 코딩 맵 범례
    has_material_map: bool = False
    has_anchor: bool = False  # 마지막 레퍼런스 = 같은 프로젝트의 기준 컷
    project_text: str = ""  # 내 설계의 프로그램·설계 논리 글
    n_project: int = 0  # 첨부하는 내 설계 도면/다이어그램 장수
    facts_strict: bool = True  # 설계 자료에 없는 내용 추가 금지
    work_type: str = "다이어그램"  # 다이어그램 / 평면 리터칭 / 단면 리터칭
    form_level: int = 1  # 0~4 (FORM_LABELS)


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
    text = f"Form change level {FORM_LABELS[s.form_level][2:]} ({s.form_level + 1}/5): {FORM_EN[s.form_level]}"
    if s.work_type in DRAWING_RULES_EN:
        text += "\n" + DRAWING_RULES_EN[s.work_type]
    return text


def style_en(s: Spec) -> str:
    lines = [f"- Reference strength ({s.style_strength}): {STRENGTH_EN[s.style_strength]}"]
    if s.has_anchor:
        lines.append("- " + ANCHOR_EN)
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
        images = (f"- 1_sketch.png = {INPUT_EN[s.work_type]}\n"
                  f"- {ref_names(n_refs)} = STYLE references only — never copy their buildings or content")
    else:
        images = f"- 1_sketch.png = {INPUT_EN[s.work_type]}. No reference images."
    if s.n_project and board:
        images += " Panels labeled 'PROJECT n = FACTS' are my own design drawings: content facts only."
    elif s.n_project:
        images += f"\n- {project_names(s.n_project)} = MY DESIGN DRAWINGS (content facts only, not style)"
    if s.has_material_map:
        images += ("\n- 4_material_map.png = MATERIAL ID MAP (same camera; flat colors = materials)" if not board
                   else " The panel labeled 'MATERIAL MAP' is a material ID map of the same camera view.")
    aspect = f" Aspect ratio: {ASPECT_EN[s.aspect]}." if ASPECT_EN.get(s.aspect) else ""
    think = f"\n{THINK_EN[s.think]}" if THINK_EN.get(s.think) else ""
    steps = "Generate the image."
    return f"""Create a presentation-ready {WORK_EN[s.work_type]} from the attached image(s).
If the images are not attached yet, reply only "이미지를 첨부해 주세요" and wait for my next message with the images.
{ref_guard_en(n_refs, board)}

ATTACHED
{images}

PRIORITY 1 — what it must communicate (overrides style):
{goal_en(s)}
{facts_en(s)}

PRIORITY 2 — structure:
{structure_en(s)}
{render_en(s)}

{style_header_en(s)}
{style_en(s)}

{DETAIL_EN[s.detail]}

STEPS
{steps} {QUALITY_EN[s.quality]}{aspect}{think}
{f"Extra instruction: {s.extra}" if s.extra else ""}
{EFFICIENCY_EN}

For my later revision requests: keep everything from the previous image unchanged except what I ask to change.
Keep any text labels exactly as written in the sketch."""


# ---------------------------------------------------------------- ChatGPT (한국어)
def chatgpt_ko(s: Spec, n_refs: int, board: bool) -> str:
    if board:
        images = ("첨부한 보드 이미지 한 장: 왼쪽 'SKETCH = CONTENT' 칸이 그릴 내용, 오른쪽 'REF n = STYLE ONLY' 칸들은 "
                  "스타일 레퍼런스. 결과는 보드가 아니라 스케치를 다시 그린 이미지 한 장만.")
    elif n_refs:
        images = (f"- 1_sketch.png = {INPUT_KO[s.work_type]}\n"
                  f"- {ref_names(n_refs)} = 스타일 레퍼런스 (형태는 절대 복사하지 말 것)")
    else:
        images = f"- 1_sketch.png = {INPUT_KO[s.work_type]}. 레퍼런스 이미지는 없음."
    if s.n_project and board:
        images += " 'PROJECT n = FACTS' 칸은 내 설계 도면: 내용의 기준으로만 사용."
    elif s.n_project:
        images += f"\n- {project_names(s.n_project)} = 내 설계 도면 (내용의 기준, 스타일 아님)"
    if s.has_material_map:
        images += ("\n- 4_material_map.png = 재료 색 코딩 맵 (같은 카메라, 단색 = 재료)" if not board
                   else " 'MATERIAL MAP' 칸은 같은 카메라의 재료 색 코딩 맵.")
    goal = "\n".join(x for x in [
        f"- 유형: {', '.join(s.types)}" if s.types else "",
        f"- 설명: {s.goal}" if s.goal else "",
    ] if x) or "- 스케치를 보고 판단"
    style = "\n".join(x for x in [
        f"- 레퍼런스 강도({s.style_strength}): {STRENGTH_KO[s.style_strength]}",
        f"- {ANCHOR_KO}" if s.has_anchor else "",
        f"- 스타일 키워드: {', '.join(s.keywords)}" if s.keywords else "",
        f"- 원하는 느낌: {s.mood}" if s.mood else "",
        f"- 스타일 가이드:\n{s.style_guide}" if s.style_guide else "",
    ] if x) or "- 레퍼런스 이미지의 그래픽 스타일을 따를 것"
    rule = f"형태 변형 단계 {FORM_LABELS[s.form_level]}: {FORM_KO[s.form_level]}" + (
        f"\n{DRAWING_RULES_KO[s.work_type]}" if s.work_type in DRAWING_RULES_KO else "")
    ratio = f" 비율은 {s.aspect}." if s.aspect != "자동" else ""
    steps = "이미지를 생성해줘."
    return f"""첨부 이미지로 {WORK_KO[s.work_type]}을(를) 만들어줘.
아직 이미지가 첨부되지 않았다면 "이미지를 첨부해 주세요"라고만 답하고 다음 메시지를 기다려줘.
{ref_guard_ko(n_refs, board)}

[첨부]
{images}

[1순위 · {"어떤 다이어그램인지" if s.work_type == "다이어그램" else ("어떤 렌더링인지" if s.work_type == "렌더링" else "어떤 리터칭인지")} — 스타일보다 우선]
{goal}
{facts_ko(s)}

[2순위 · 구조] {rule}
{render_ko(s)}

[3순위 · 스타일 — {"엄격히 따를 것 (형태는 스케치 유지)" if s.style_strength == "스타일 우선" else "1, 2순위와 충돌하지 않는 범위에서"}]
{style}

{DETAIL_KO[s.detail]}

[진행]
{steps} {QUALITY_KO[s.quality]}{ratio} {THINK_KO.get(s.think, "")}
{f"추가 지시: {s.extra}" if s.extra else ""}
{EFFICIENCY_KO}

이후 수정 요청을 하면, 요청한 부분 외에는 직전 이미지를 그대로 유지해서 다시 생성해줘."""


# ---------------------------------------------------------------- API 이미지 모델 (영어)
def image_api(s: Spec, n_refs: int, task: str) -> str:
    rng = lambda a, b: f"{a}" if a == b else f"{a}–{b}"  # noqa: E731
    refs = (f"IMAGE {rng(2, n_refs + 1)} = style references ONLY. Never copy their buildings or content."
            if n_refs else "No reference images; follow the style text.")
    if s.n_project:
        refs += (f"\nIMAGE {rng(n_refs + 2, n_refs + 1 + s.n_project)} = MY DESIGN DRAWINGS of this project: "
                 "content facts only, not style.")
    return f"""You are making a {WORK_EN[s.work_type]}.
IMAGE 1 = {INPUT_EN[s.work_type]} (or a previous version of the result).
{refs}

PRIORITY 1 — what it must communicate (overrides style):
{goal_en(s)}
{facts_en(s).replace(project_names(s.n_project), "the design drawings") if s.n_project else facts_en(s)}

PRIORITY 2 — structure:
{structure_en(s)}
{render_en(s).replace("4_material_map.png", "the material ID map image (last image)")}

{style_header_en(s)}
{style_en(s)}

{DETAIL_EN[s.detail]}

Task: {task}
{QUALITY_EN[s.quality]} Keep any text labels exactly as in the sketch."""


# ---------------------------------------------------------------- Claude(구독)에게 보낼 검토 요청
def claude_review_request(draft: str, context_ko: str, n_refs: int, board: bool, n_project: int = 0,
                          has_map: bool = False) -> str:
    if board:
        att = ("ONE board image: left panel 'SKETCH' = content to draw, right panels 'REF n' = style references"
               + (", 'PROJECT n' panels = my design drawings (content facts)." if n_project else "."))
    else:
        att = f"Image 1 = SKETCH (content to draw)" + (f", images 2–{n_refs + 1} = style REFERENCES" if n_refs else "")
        att += (f", images {n_refs + 2}–{n_refs + 1 + n_project} = MY DESIGN DRAWINGS (content facts)." if n_project else ".")
    if has_map:
        att += " The last image (or the 'MATERIAL MAP' panel) is a MATERIAL ID MAP of the same camera view."
    return f"""Act as a senior architectural-diagram art director and prompt engineer.
I will paste the images right after this message. If they are not attached yet, reply only "이미지를 첨부해 주세요" and wait.
Attached: {att}

Review the DRAFT prompt below (it will be pasted into ChatGPT together with the same images) and improve it:
1. Read the sketch: list what must be preserved (number/order/layout of steps, viewpoint, site boundary, key masses, voids/courtyards, arrows, text) and add them as explicit constraints.
2. Read the references: extract the concrete graphic language (accent colors as hex, line weights, fills, label typography/layout, arrow types, tree/people style, background, and elements they do NOT use such as titles or legends) and add precise rules.
3. Fix conflicts between the goal, keywords, mood, style strength and references; remove vague or redundant wording.
4. If project documents are given (my design drawings and/or program text): extract the FACTS (program and space names, numbers, areas, floor counts, labels, key design logic), state the ones the diagram needs in the prompt, and remove or correct anything that contradicts them or is not supported by them.
5. If the work type is a floor plan or section retouch: make sure the prompt locks the drawing geometry (walls, openings, levels, text) at the chosen form change level and only lists rendering operations.
7. If the work type is a rendering: make sure the prompt locks the camera and building geometry (opening counts, mullion pattern, edges), states the materials exactly (and the material ID map legend if given), one consistent light direction and time of day.
6. Respect the detail level: do not add requests for extra detail (e.g. clothing fabric, faces, textures on entourage). Keep the prompt's "WORK EFFICIENTLY" line so the image model makes one image without self-review.
Keep the draft's language, its attachment description, its missing-image guard lines and the "reply in Korean" line. Keep it under ~2,500 characters. Do not invent design content.

Answer in Korean: first a short list of the problems you found (most important first), then the improved prompt inside ONE code block (```) so I can copy it.

USER SETTINGS:
{context_ko}

DRAFT PROMPT:
{draft}"""


# ---------------------------------------------------------------- Claude Code(구독, CLI)용 검토 요청
MARK_START, MARK_END = "=== IMPROVED PROMPT START ===", "=== IMPROVED PROMPT END ==="


def claude_cli_request(draft: str, context_ko: str, sketch: str, refs: list[str],
                       projects: list[str] | None = None, extras: list[tuple[str, str]] | None = None) -> str:
    files = f"- {sketch} = SKETCH (content to draw)\n" + "".join(f"- {r} = REFERENCE {i} (style only)\n"
                                                              for i, r in enumerate(refs, 1))
    files += "".join(f"- {p} = MY DESIGN DRAWING {i} (content facts)\n" for i, p in enumerate(projects or [], 1))
    files += "".join(f"- {n} = {label}\n" for n, label in extras or [])
    return f"""Act as a senior architectural-diagram art director and prompt engineer.
The images are files in the current directory. Use the Read tool to look at EVERY one of them before reviewing:
{files}
Review the DRAFT prompt below. It will be sent to ChatGPT/Codex (image generation) together with the same image files.
1. Read the sketch: list what must be preserved (number/order/layout of steps, viewpoint, site boundary, key masses, voids/courtyards, arrows, text) and add them as explicit constraints.
2. Read the references: extract the concrete graphic language (accent colors as hex, line weights, fills, label typography/layout, arrow types, tree/people style, background, and elements they do NOT use such as titles or legends) and add precise rules.
3. Fix conflicts between the goal, keywords, mood, style strength and references; remove vague or redundant wording.
4. If project documents are given (my design drawings and/or program text): extract the FACTS (program and space names, numbers, areas, floor counts, labels, key design logic), state the ones the diagram needs in the prompt, and remove or correct anything that contradicts them or is not supported by them.
5. If the work type is a floor plan or section retouch: make sure the prompt locks the drawing geometry (walls, openings, levels, text) at the chosen form change level and only lists rendering operations.
7. If the work type is a rendering: make sure the prompt locks the camera and building geometry (opening counts, mullion pattern, edges), states the materials exactly (and the material ID map legend if given), one consistent light direction and time of day.
6. Respect the detail level: do not add requests for extra detail (e.g. clothing fabric, faces, textures on entourage). Keep the prompt's "WORK EFFICIENTLY" line so the image model makes one image without self-review.
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
5. Facts: if project documents are given, every program/space name, number, floor count, label and design move in the result must be supported by them or the sketch. Flag anything invented or contradicting them.
6. Drawing accuracy (when the work type is a floor plan or section retouch): compared with the original drawing (SKETCH), walls and their thickness, doors, windows, stairs, columns/grid, levels, room names, areas and dimensions must be unchanged and the view must stay orthographic. Flag any moved, missing, added or distorted element.
7. Rendering (when the work type is a rendering): same camera/viewpoint/perspective as the model view; massing, edges and roof lines unchanged; number, size and pattern of windows, doors and mullions unchanged; materials match the specified materials / material ID map; one consistent light and shadow direction; people and cars at correct scale; no AI artifacts (warped or melted geometry, bent windows, garbled text). If a DIFF MAP is given: red = model edges missing in the result, blue = new edges in the result — use it to locate geometry changes (small noise from textures, people and trees is normal).
Respect the form change level in the user settings: at levels 1-2 any geometric change is a problem; at levels 4-5 simplification is allowed but the concept must remain.
Respect the detail level in the user settings: never ask for more detail than it allows (simple, realistic entourage without clothing textures or faces is intended); flag excessive detail only if it distracts from the message.
Only flag problems that clearly matter for a presentation drawing. If it is good enough, PASS."""


def qa_request_cli(result: str, sketch: str, refs: list[str], context_ko: str, prompt_used: str,
                   projects: list[str] | None = None, extras: list[tuple[str, str]] | None = None) -> str:
    files = (f"- {result} = GENERATED RESULT (to check)\n- {sketch} = original SKETCH / input\n"
             + "".join(f"- {r} = STYLE REFERENCE {i}\n" for i, r in enumerate(refs, 1))
             + "".join(f"- {p} = MY DESIGN DRAWING {i} (content facts)\n" for i, p in enumerate(projects or [], 1))
             + "".join(f"- {n} = {label}\n" for n, label in extras or []))
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


# ---------------------------------------------------------------- 렌더링: 나눠서 생성 (3단계)
PASSES_EN = [
    "PASS 1 of 3 — BUILDING ONLY: apply the materials and the lighting to the building. Keep the sky and surroundings "
    "plain and neutral (light grey). No people, no cars, no trees.",
    "PASS 2 of 3 — SKY & CONTEXT: edit the attached image. Add the sky, ground, landscape and surrounding context in "
    "the same light. Keep the building exactly as it is (geometry, materials, lighting). Still no people or cars.",
    "PASS 3 of 3 — ENTOURAGE: edit the attached image. Add people, cars and small landscape elements at correct scale "
    "following the detail level. Keep everything else exactly as it is.",
]
PASS_NAMES = ["1/3 건물 재료·조명", "2/3 하늘·배경", "3/3 첨경"]
