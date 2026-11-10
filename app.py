"""
건축 다이어그램 에이전트 (프로토타입)

우선순위:  ① 어떤 다이어그램인지  >  ② 스케치 구조  >  ③ 분위기·레퍼런스 스타일
 - 분위기 문장을 쓰면 구절마다 '대체 키워드'를 실시간 추천 (Gemini 무료 / 기본 사전)
 - 생성: ChatGPT 구독 모드(프롬프트+이미지 준비 → ChatGPT) 또는 API 모드(앱에서 바로)
 - 결과: 클립보드 복사 / outputs 자동 저장 / PPT 내보내기
"""

import base64
import io
import os
import re
from urllib.parse import urlencode
from pathlib import Path

import streamlit as st
from openai import OpenAI
from PIL import Image
from st_keyup import st_keyup

import io_bridge as bridge
import claude_cli
import claude_review
import codex_bridge
import llm
import prompts
from keywords import DEFAULT_KEYWORDS, ko, suggest_by_phrase, suggest_for_phrase

APP_DIR = Path(__file__).parent
KEY_FILE = APP_DIR / "api_key.txt"
GEMINI_KEY_FILE = APP_DIR / "gemini_key.txt"
CLAUDE_KEY_FILE = APP_DIR / "claude_key.txt"
OUT_DIR = APP_DIR / "outputs"
TO_GPT_DIR = APP_DIR / "to_chatgpt"
CODEX_DIR = APP_DIR / "to_codex"
CHATGPT_URL = "https://chatgpt.com/"
CLAUDE_URL = "https://claude.ai/new"
DEFAULT_INBOX = APP_DIR / "inbox"
DEFAULT_INBOX.mkdir(exist_ok=True)

DIAGRAM_TYPES = ["매스 형성 과정", "프로그램 조닝", "동선", "분해 액소", "환경 (빛·바람)",
                 "단면 다이어그램", "배치·맥락", "구조·재료", "컨셉 다이어그램", "단계별 시퀀스"]
QUALITY = {  # 화면 표시: (API quality, ChatGPT 지시문)
    "초안 (빠름)": ("low", "빠르게 확인할 러프 초안 수준으로 (디테일 최소)"),
    "표준": ("medium", "발표용 표준 품질로"),
    "고화질": ("high", "최고 품질로: 가능한 최대 해상도, 선과 글자를 선명하게, 질감과 디테일을 충실하게"),
}
ASPECT = {"자동": "auto", "가로 (3:2)": "1536x1024", "세로 (2:3)": "1024x1536", "정사각형": "1024x1024"}

st.set_page_config(page_title="건축 다이어그램 에이전트", layout="wide")
st.markdown(  # 키워드 버튼이 옆으로 잘리지 않고 줄바꿈되게
    "<style>[data-testid='stButtonGroup'] > div {flex-wrap: wrap; overflow-x: visible;}</style>",
    unsafe_allow_html=True,
)

ss = st.session_state
for k, v in {
    "style_guide": "", "versions": [], "chat": [], "picked": [], "pasted_refs": [],
    "sketch_bytes": None, "sketch_src": None, "mood": "", "mood_ver": 0,
}.items():
    ss.setdefault(k, v)


def _read(p: Path) -> str:
    return p.read_text().strip() if p.exists() else ""


@st.cache_data(ttl=600, show_spinner=False)
def claude_login_status() -> str:
    return claude_cli.login_status()


@st.cache_data(ttl=600, show_spinner=False)
def claude_code_status() -> str:
    return claude_cli.claude_version()


@st.cache_data(ttl=600, show_spinner=False)
def codex_login_status() -> str:
    return codex_bridge.login_status()


@st.cache_data(ttl=600, show_spinner=False)
def codex_status() -> str:
    return codex_bridge.codex_version()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def gemini_models(key: str) -> list[str]:
    return llm.list_gemini_models(key)


# ---------------------------------------------------------------- 설정
with st.sidebar:
    st.header("설정")
    saved_key = _read(KEY_FILE)
    env_key = os.getenv("OPENAI_API_KEY", saved_key)
    mode = st.radio(
        "생성 방식",
        ["ChatGPT 구독 모드", "Codex 자동 (구독)", "API 모드"],
        index=2 if env_key else (1 if codex_bridge.find_codex() else 0),
        help="ChatGPT 구독: 앱이 준비 → ChatGPT 창에서 붙여넣어 생성\n\n"
        "Codex 자동: ChatGPT 구독으로 로그인한 Codex가 앱 안에서 자동 생성 (GPT-6 Astra 등 사용)\n\n"
        "API 모드: 앱 안에서 바로 생성 (OpenAI API 키 필요, 사용량만큼 과금)",
    )
    use_api = mode == "API 모드"
    use_codex = mode.startswith("Codex")
    use_chatgpt = mode == "ChatGPT 구독 모드"
    api_key = ""
    if use_api:
        api_key = st.text_input("OpenAI API Key", value=env_key, type="password")
        if api_key and api_key != saved_key and st.button("OpenAI 키 저장"):
            KEY_FILE.write_text(api_key)
            st.success("저장했어요.")

    think, open_target, attach_mode, prompt_lang = "자동", "Chrome", "파일 여러 장", "English (추천)"
    codex_model = "gpt-6-astra"
    pipe_engine, cc_model, cc_ver = "검토 없이", "Opus (가장 꼼꼼)", ""
    if use_codex:
        ver = codex_status()
        if ver:
            login = codex_login_status()
            st.caption(f"✅ Codex 설치됨 ({ver}) · {login}")
            if not login.startswith("로그인됨") and st.button("🔑 Codex 로그인 (Chrome으로 열기)"):
                try:
                    url = codex_bridge.start_login(bridge.open_url)
                    st.info("Chrome에서 ChatGPT 계정으로 로그인을 마친 뒤 '로그인 상태 새로고침'을 누르세요.\n\n"
                            f"Chrome이 안 열리면 이 주소를 Chrome에 붙여넣기:\n\n{url}")
                except RuntimeError as e:
                    st.error(str(e))
            if st.button("로그인 상태 새로고침"):
                codex_login_status.clear()
                st.rerun()
        else:
            st.warning(codex_bridge.SETUP_HELP)
        codex_model = st.text_input("Codex 모델", "gpt-6-astra",
                                    help="Codex에서 쓸 모델 이름. 예: gpt-6-astra. 이미지는 Codex 내장 이미지 생성으로 만들어요.")
        think = st.select_slider("생각 수준", options=["빠르게", "자동", "깊게 생각"], value="자동",
                                 help="Codex 추론 강도 (low / medium / high)")
        prompt_lang = st.radio("프롬프트 언어", ["English (추천)", "한국어"], horizontal=True)
        st.markdown("**🤖 원클릭 전체 자동**")
        cc_ver = claude_code_status()
        engines = ["Claude Code (구독)", "Claude API", "검토 없이"]
        pipe_engine = st.radio("원클릭 검토 엔진", engines,
                               index=0 if cc_ver else (1 if os.getenv("ANTHROPIC_API_KEY") or CLAUDE_KEY_FILE.exists() else 2),
                               help="Claude Code (구독): Claude 구독으로 로그인한 Claude Code가 이미지를 직접 보고 검토\n\n"
                                    "Claude API: 아래 'Claude API 키' 사용 (사용량 과금)")
        cc_model = "Opus (가장 꼼꼼)"
        if pipe_engine.startswith("Claude Code"):
            if cc_ver:
                cc_login = claude_login_status()
                st.caption(f"✅ Claude Code 설치됨 ({cc_ver}) · {cc_login}")
                if not cc_login.startswith("로그인됨") and st.button("🔑 Claude Code 로그인 (Chrome으로 열기)"):
                    try:
                        url = claude_cli.start_login(bridge.open_url)
                        st.info("Chrome에서 Claude 구독 계정으로 로그인을 마친 뒤 '로그인 상태 새로고침'을 누르세요.\n\n"
                                f"Chrome이 안 열리면 이 주소를 Chrome에 붙여넣기:\n\n{url}")
                    except RuntimeError as e:
                        st.error(str(e))
                if st.button("로그인 상태 새로고침", key="cc_login_refresh"):
                    claude_login_status.clear()
                    st.rerun()
            else:
                st.warning(claude_cli.SETUP_HELP)
            cc_model = st.selectbox("Claude Code 모델", list(claude_cli.MODELS))
    if use_chatgpt:
        open_target = st.radio("ChatGPT 여는 곳", ["Chrome", "ChatGPT 데스크탑 앱", "기본 브라우저"],
                               help="Chrome/브라우저: 입력창에 프롬프트를 미리 채워서 열어요.\n\n"
                                    "데스크탑 앱: 앱을 열고, 프롬프트는 버튼으로 복사해 붙여넣어요.")
        think = st.select_slider("ChatGPT 생각 수준", options=["빠르게", "자동", "깊게 생각"], value="자동",
                                 help="프롬프트에 생각 깊이 지시를 넣어요. 확실하게 하려면 ChatGPT 화면 상단 "
                                      "모델 메뉴에서도 같은 수준(예: Thinking)을 골라주세요.")
        attach_mode = st.radio("이미지 첨부 방식", ["파일 여러 장", "한 장으로 합치기"],
                               help="파일 여러 장: 스케치·레퍼런스를 각각 첨부 (화질 좋음)\n\n"
                                    "한 장으로 합치기: 붙여넣기가 잘 안 될 때. 스케치+레퍼런스를 라벨 붙인 보드 1장으로")
        prompt_lang = st.radio("프롬프트 언어", ["English (추천)", "한국어"], horizontal=True,
                               help="AI는 영어 지시를 더 정확히 따르는 편이에요. ChatGPT 답변은 한국어로 오게 해뒀어요.")
    quality_label = st.select_slider("화질", options=list(QUALITY), value="표준")
    aspect = st.selectbox("비율", list(ASPECT), index=1)
    fidelity = st.radio(
        "스케치 구조 유지",
        ["엄격 (선·비율 그대로)", "보통 (정리 허용)"],
        help="엄격: 매스·동선·배치를 바꾸지 않음. 보통: 선을 정돈하고 비율을 다듬는 것 허용.",
    )
    style_strength = st.select_slider(
        "레퍼런스 스타일 강도", options=["구조 우선", "균형", "스타일 우선"], value="균형",
        help="구조 우선: 레퍼런스는 느슨한 참고\n\n균형: 색·선·라벨·화살표를 가깝게 따름\n\n"
             "스타일 우선: 레퍼런스의 그래픽 언어만 사용, 레퍼런스에 없는 제목·범례 등은 추가 금지 (형태는 스케치 유지)",
    )

    st.divider()
    st.subheader("프롬프트 검토 (Claude)")
    saved_c = _read(CLAUDE_KEY_FILE)
    env_c = os.getenv("ANTHROPIC_API_KEY", saved_c)
    review_mode = st.radio(
        "검토 방식", ["Claude 구독 (직접 확인)", "Claude API (자동)"], index=1 if env_c else 0,
        help="구독: Claude 웹/앱이 열리고 직접 확인 → 검토본을 복사해 가져오기 (추가 비용 없음)\n\n"
             "API: 앱 안에서 자동 검토 (API 키 필요, 사용량 과금)",
    )
    claude_sub = review_mode.startswith("Claude 구독")
    claude_key, claude_model_label, claude_effort, claude_target = "", list(claude_review.MODELS)[0], "high", "Chrome"
    if claude_sub:
        claude_target = st.radio("Claude 여는 곳", ["Chrome", "Claude 데스크탑 앱", "기본 브라우저"])
        st.caption("ChatGPT로 보내기 전에 Claude가 스케치·레퍼런스를 보고 프롬프트를 고쳐줘요. Claude 구독 사용량 안에서 동작해요.")
    else:
        claude_key = st.text_input(
            "Claude API Key (사용량 과금)", value=env_c, type="password",
            help="https://platform.claude.com 에서 발급. Claude 구독(Pro)과는 별도 결제예요.",
        )
        if claude_key and claude_key != saved_c and st.button("Claude 키 저장"):
            CLAUDE_KEY_FILE.write_text(claude_key)
            st.success("저장했어요.")
        claude_model_label = st.selectbox("검토 모델", list(claude_review.MODELS))
        claude_effort = st.select_slider("검토 깊이", options=["low", "medium", "high"], value="high",
                                         help="깊을수록 꼼꼼하지만 느리고 비용이 늘어요.")
        st.caption("1회 대략 Opus 100–200원 · Sonnet 50–100원 · Haiku 10원 미만 (이미지 수에 따라 다름).")

    st.divider()
    st.subheader("실시간 추천 · 분석 (Gemini)")
    saved_g = _read(GEMINI_KEY_FILE)
    gemini_key = st.text_input(
        "Gemini API Key (무료 등급)",
        value=os.getenv("GEMINI_API_KEY", saved_g),
        type="password",
        help="https://aistudio.google.com/apikey 에서 구글 계정으로 무료 발급",
    )
    if gemini_key and gemini_key != saved_g and st.button("Gemini 키 저장"):
        GEMINI_KEY_FILE.write_text(gemini_key)
        st.success("저장했어요.")
    st.caption("키가 없으면 기본 사전으로 추천해요. 무료 등급은 입력 내용이 구글 서비스 개선에 쓰일 수 있으니 "
               "미공개 프로젝트 이미지를 '가이드 생성'에 넣을 땐 주의하세요.")

    with st.expander("고급 (모델 · 폴더)"):
        inbox = Path(
            st.text_input(
                "스케치 받을 폴더",
                value=str(DEFAULT_INBOX),
                help="라이노/스케치업 내보내기 폴더나 윈도우 '사진\\스크린샷' 폴더를 지정하면 편해요.",
            )
        )
        gemini_fast = gemini_vision = ""
        fast_fallbacks = vision_fallbacks = ()
        if gemini_key:
            try:
                g_models = gemini_models(gemini_key)
            except Exception as e:  # noqa: BLE001
                g_models = []
                st.error(f"Gemini 모델 목록을 못 불러왔어요 (키 확인): {str(e)[:120]}")
            if g_models:
                fast_default = llm.pick_gemini_model(g_models, lite=True)
                vision_default = llm.pick_gemini_model(g_models, lite=False)
                gemini_fast = st.selectbox("Gemini 추천 모델", g_models, index=g_models.index(fast_default))
                gemini_vision = st.selectbox("Gemini 분석 모델", g_models, index=g_models.index(vision_default))
                fast_fallbacks = tuple(llm.rank_gemini_models(g_models, lite=True))
                vision_fallbacks = tuple(llm.rank_gemini_models(g_models, lite=False))
                st.caption("선택한 모델이 붐비면 다른 Flash 모델로 자동 전환해요.")
        url_model = st.text_input("ChatGPT 주소에 넣을 모델 값 (선택)", "",
                                  help="예: gpt-5-thinking. 비워두면 ChatGPT 기본 모델. "
                                       "공식 기능이 아니라 무시될 수 있어요.")
        image_model = st.selectbox("OpenAI 이미지 모델 (API 모드)", ["gpt-image-1", "gpt-image-1-mini"],
                                   help="mini: 더 싸고 빠름, 품질은 조금 낮음")
        vision_model = st.text_input("OpenAI 분석 모델 (API 모드)", "gpt-4o")
    if st.button("세션 초기화"):
        st.session_state.clear()
        st.rerun()

has_llm = bool((gemini_key and gemini_vision) or (use_api and api_key))


def llm_keys(fast: bool = False) -> dict:
    return dict(
        gemini_key=gemini_key if gemini_vision else "",
        gemini_model=gemini_fast if fast else gemini_vision,
        gemini_fallbacks=fast_fallbacks if fast else vision_fallbacks,
        on_fallback=lambda m: st.toast(f"모델이 붐벼서 {m}(으)로 처리했어요."),
        openai_key=api_key if use_api else "",
        openai_model=vision_model,
    )


def clipboard_or_warn() -> bytes | None:
    try:
        b = bridge.grab_clipboard()
    except Exception as e:  # noqa: BLE001
        st.error(f"클립보드를 읽지 못했어요: {e}")
        return None
    if b is None:
        st.warning("클립보드에 이미지가 없어요. 먼저 캡처/복사한 뒤 눌러주세요.")
    return b


@st.cache_data(ttl=3600, show_spinner=False)
def gemini_suggest(text: str, goal: str, key: str, model: str, fallbacks: tuple[str, ...]):
    return llm.phrase_keywords(text, goal, gemini_key=key, gemini_model=model, gemini_fallbacks=fallbacks)


# ---------------------------------------------------------------- 프롬프트 재료
def goal_text() -> str:
    parts = []
    if ss.get("diagram_types"):
        parts.append("유형: " + ", ".join(ss.diagram_types))
    if ss.get("diagram_goal"):
        parts.append("설명: " + ss.diagram_goal)
    return "\n".join(parts)


def mood_text() -> str:
    parts = []
    if ss.mood:
        parts.append(f"원하는 느낌: {ss.mood}")
    if ss.picked:
        parts.append("스타일 키워드: " + ", ".join(ss.picked))
    if ss.style_guide:
        parts.append("스타일 가이드:\n" + ss.style_guide)
    return "\n".join(parts)


def to_png_file(data: bytes, name: str) -> tuple[str, bytes, str]:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((2048, 2048))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def spec(extra: str = "") -> prompts.Spec:
    return prompts.Spec(
        types=list(ss.get("diagram_types") or []), goal=ss.get("diagram_goal", ""), mood=ss.mood,
        keywords=list(ss.picked), style_guide=ss.style_guide, strict=fidelity.startswith("엄격"),
        quality=quality_label, aspect=aspect, think=think, extra=extra, style_strength=style_strength,
    )


# ---------------------------------------------------------------- API 모드 생성
def render(base_png: bytes, ref_bytes: list[bytes], instruction: str) -> bytes:
    prompt = prompts.image_api(spec(), bool(ref_bytes), instruction)
    files = [to_png_file(base_png, "base.png")] + [to_png_file(b, f"ref{i}.png") for i, b in enumerate(ref_bytes)]
    kwargs = dict(model=image_model, image=files, prompt=prompt,
                  size=ASPECT[aspect], quality=QUALITY[quality_label][0])
    client = OpenAI(api_key=api_key)
    try:
        r = client.images.edit(**kwargs, input_fidelity="high")
    except TypeError:  # 구버전 SDK
        r = client.images.edit(**kwargs)
    return base64.b64decode(r.data[0].b64_json)


# ---------------------------------------------------------------- ChatGPT 구독 모드
def chatgpt_prompt(n_refs: int, extra: str) -> str:
    board = attach_mode == "한 장으로 합치기"
    build = prompts.chatgpt_en if prompt_lang.startswith("English") else prompts.chatgpt_ko
    return build(spec(extra), n_refs, board)


def copy_attachments() -> None:
    """준비된 첨부 이미지를 클립보드에 (파일 여러 장 또는 보드 한 장)."""
    if attach_mode == "한 장으로 합치기":
        bridge.copy_to_clipboard((TO_GPT_DIR / "board.png").read_bytes())
    else:
        bridge.copy_files(sorted(p for p in TO_GPT_DIR.iterdir() if p.name != "board.png"))


def review_context() -> str:
    return "\n".join([
        f"- 다이어그램 유형: {', '.join(ss.get('diagram_types') or []) or '미지정'}",
        f"- 다이어그램 설명: {ss.get('diagram_goal') or '없음'}",
        f"- 원하는 느낌: {ss.mood or '없음'}",
        f"- 선택 키워드: {', '.join(ss.picked) or '없음'}",
        f"- 스케치 구조 유지: {fidelity} / 레퍼런스 스타일 강도: {style_strength}",
        f"- 이미지 첨부 방식: {attach_mode} / 화질: {quality_label} / 비율: {aspect} / 생각 수준: {think}",
    ])


def run_review(ref_bytes: list[bytes], draft: str) -> None:
    model = claude_review.MODELS[claude_model_label]
    try:
        with st.spinner(f"Claude({claude_model_label})가 스케치·레퍼런스를 보며 검토 중... (30초~2분)"):
            result = claude_review.review(claude_key, model, claude_effort, draft, review_context(),
                                          ss.sketch_bytes, ref_bytes)
        ss.review = {"draft": draft, **result}
        ss.reviewed_text = result["improved_prompt"]
    except RuntimeError as e:
        st.error(str(e))


def prepare_attachments(ref_bytes: list[bytes]) -> None:
    """to_chatgpt 폴더에 첨부 이미지를 만들고 클립보드에 복사 (ChatGPT·Claude 공용)."""
    bridge.write_images(TO_GPT_DIR, [("1_sketch.png", ss.sketch_bytes)]
                        + [(f"2_reference_{i + 1}.png", b) for i, b in enumerate(ref_bytes)])
    if attach_mode == "한 장으로 합치기":
        (TO_GPT_DIR / "board.png").write_bytes(bridge.make_board(ss.sketch_bytes, ref_bytes))
    try:
        copy_attachments()
        ss.clip_ok = True
    except Exception as e:  # noqa: BLE001
        ss.clip_ok = False
        st.warning(f"이미지 자동 복사 실패 ({str(e)[:100]}) — `to_chatgpt` 폴더에서 끌어다 놓아 주세요.")
        try:
            bridge.open_folder(TO_GPT_DIR)
        except Exception:  # noqa: BLE001
            pass


def send_to_claude(ref_bytes: list[bytes], draft: str) -> None:
    """Claude(구독)를 열고 검토 요청을 미리 채움. 이미지는 클립보드에."""
    request = prompts.claude_review_request(draft, review_context(), len(ref_bytes),
                                            attach_mode == "한 장으로 합치기")
    ss.claude_request, ss.claude_draft = request, draft
    prepare_attachments(ref_bytes)
    ss.claude_prefilled = False
    if claude_target == "Claude 데스크탑 앱":
        try:
            bridge.open_desktop_app("Claude")
            ss.claude_opened = "desktop"
            return
        except Exception as e:  # noqa: BLE001
            st.warning(f"{e} → Chrome으로 열게요.")
    url = f"{CLAUDE_URL}?{urlencode({'q': request})}"
    if len(url) > 8000:
        url = CLAUDE_URL
    else:
        ss.claude_prefilled = True
    ss.claude_opened = bridge.open_url(url, prefer_chrome=claude_target != "기본 브라우저")


def import_claude_review() -> None:
    try:
        text = bridge.grab_text()
    except Exception as e:  # noqa: BLE001
        st.error(f"클립보드를 읽지 못했어요: {e}")
        return
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    prompt_text = (max(blocks, key=len) if blocks else text).strip()
    if len(prompt_text) < 200:
        st.warning("클립보드에 검토된 프롬프트가 없는 것 같아요. Claude 답변의 코드 블록 복사 버튼을 누른 뒤 다시 시도하세요.")
        return
    ss.review = {"draft": ss.claude_draft, "summary_ko": "Claude(구독)에서 검토한 프롬프트를 가져왔어요. "
                 "문제 목록은 Claude 대화창에서 확인하세요.", "issues": [], "sketch_reading_ko": "",
                 "reference_style_ko": "", "improved_prompt": prompt_text, "model_used": "Claude 구독"}
    ss.reviewed_text = prompt_text
    st.toast("검토본을 가져왔어요. 이제 🚀 ChatGPT로 보내기를 누르세요.")


def _codex_refs(ref_bytes: list[bytes]) -> list[str]:
    names = [f"2_reference_{i + 1}.png" for i in range(len(ref_bytes))]
    CODEX_DIR.mkdir(exist_ok=True)
    for n, b in zip(names, ref_bytes):
        if not (CODEX_DIR / n).exists():
            Image.open(io.BytesIO(b)).convert("RGB").save(CODEX_DIR / n, format="PNG")
    return names


def _codex_call(prompt: str, images: list[str], note: str, session: str | None) -> bool:
    out = f"result_v{len(ss.versions) + 1}.png"
    try:
        with st.spinner(f"Codex({codex_model})가 생성 중이에요... 보통 1~5분 걸려요. 이 창을 닫지 마세요."):
            res = codex_bridge.run(CODEX_DIR, prompt, images, out, codex_model,
                                   codex_bridge.EFFORT[think], session_id=session)
    except RuntimeError as e:
        st.error(str(e).split("\n\n")[0])
        detail = str(e).split("\n\n", 1)
        if len(detail) > 1:
            with st.expander("Codex 실행 기록"):
                st.code(detail[1], language=None)
        return False
    ss.codex_session, ss.codex_log = res["session_id"], res["log"]
    add_version(res["png"], note)
    ss.chat.append(("assistant", f"v{len(ss.versions)} 완료 ({note})."))
    return True


def codex_generate(ref_bytes: list[bytes], extra: str) -> None:
    prompt = final_prompt(chatgpt_prompt(len(ref_bytes), extra))
    ss.gpt_prompt = prompt
    bridge.write_images(CODEX_DIR, [("1_sketch.png", ss.sketch_bytes)]
                        + [(f"2_reference_{i + 1}.png", b) for i, b in enumerate(ref_bytes)])
    _codex_call(prompt, ["1_sketch.png", *_codex_refs(ref_bytes)], "Codex 생성", None)


def run_pipeline(ref_bytes: list[bytes], extra: str, draft: str) -> None:
    """원클릭: 초안 → Claude 검토 → Codex(Astra) 이미지 생성 → 결과 등록."""
    refs = [f"2_reference_{i + 1}.png" for i in range(len(ref_bytes))]
    bridge.write_images(CODEX_DIR, [("1_sketch.png", ss.sketch_bytes)] + list(zip(refs, ref_bytes)))
    prompt = draft
    with st.status("🤖 전체 자동 진행 중...", expanded=True) as status:
        st.write("✅ ① 프롬프트 초안 작성 완료")
        if pipe_engine != "검토 없이":
            st.write(f"⏳ ② Claude 검토 중 ({pipe_engine})... 1~3분")
            try:
                if pipe_engine.startswith("Claude Code"):
                    res = claude_cli.review(CODEX_DIR, draft, review_context(), "1_sketch.png", refs,
                                            claude_cli.MODELS[cc_model])
                    ss.review = {"draft": draft, "summary_ko": res["summary_ko"], "issues": [],
                                 "sketch_reading_ko": "", "reference_style_ko": "",
                                 "improved_prompt": res["improved_prompt"], "model_used": "Claude Code (구독)"}
                else:
                    key = claude_key or os.getenv("ANTHROPIC_API_KEY", "") or _read(CLAUDE_KEY_FILE)
                    if not key:
                        raise RuntimeError("Claude API 키가 없어요. 사이드바 '프롬프트 검토'에서 키를 넣어주세요.")
                    result = claude_review.review(key, claude_review.MODELS[claude_model_label], claude_effort,
                                                  draft, review_context(), ss.sketch_bytes, ref_bytes)
                    ss.review = {"draft": draft, **result}
                ss.reviewed_text = ss.review["improved_prompt"]
                prompt = ss.reviewed_text
                st.write("✅ ② Claude 검토 완료 — 검토된 프롬프트로 진행해요")
            except RuntimeError as e:
                st.write(f"⚠️ ② Claude 검토 실패 → 초안 그대로 진행: {str(e).splitlines()[0]}")
        ss.gpt_prompt = prompt
        st.write(f"⏳ ③ Codex({codex_model})로 다이어그램 생성 중... 보통 1~5분")
        ok = _codex_call(prompt, ["1_sketch.png", *refs], "원클릭 자동 생성", None)
        if ok:
            st.write("✅ ③ 이미지 생성 완료 → 아래 ④ 결과에 v" + str(len(ss.versions)) + "로 등록")
        status.update(label="🤖 완료! 아래 ④ 결과를 확인하세요" if ok else "🤖 이미지 생성 단계에서 멈췄어요",
                      state="complete" if ok else "error")


def codex_revise(base_png: bytes, idx: int, req: str, ref_bytes: list[bytes]) -> bool:
    base = f"base_v{idx + 1}.png"
    CODEX_DIR.mkdir(exist_ok=True)
    (CODEX_DIR / base).write_bytes(base_png)
    refs = _codex_refs(ref_bytes)
    prompt = (f"Revise the attached diagram `{base}` (version v{idx + 1}). Keep everything in it unchanged except "
              f"this revision: {req}\n"
              + (f"The attached {', '.join(refs)} are the style references; keep following them.\n" if refs else "")
              + "Reply in Korean.")
    return _codex_call(prompt, [base, *refs], req, ss.get("codex_session"))


def final_prompt(draft: str) -> str:
    """검토 결과가 지금 초안 기준이고 '검토본 사용'이 켜져 있으면 검토본, 아니면 초안."""
    r = ss.get("review")
    if r and r["draft"] == draft and ss.get("use_reviewed", True) and ss.get("reviewed_text"):
        return ss.reviewed_text
    return draft


def send_to_chatgpt(ref_bytes: list[bytes], extra: str) -> None:
    prompt = final_prompt(chatgpt_prompt(len(ref_bytes), extra))
    ss.gpt_prompt = prompt
    prepare_attachments(ref_bytes)

    ss.prefilled = False
    if open_target == "ChatGPT 데스크탑 앱":
        try:
            bridge.open_chatgpt_desktop()
            ss.opened = "desktop"
            return
        except Exception as e:  # noqa: BLE001
            st.warning(f"{e} → Chrome으로 열게요.")
    params = {"q": prompt} | ({"model": url_model} if url_model else {})
    url = f"{CHATGPT_URL}?{urlencode(params)}"
    if len(url) > 8000:  # 너무 길면 주소로 못 보냄 → 직접 붙여넣기
        url = CHATGPT_URL
    else:
        ss.prefilled = True
    ss.opened = bridge.open_url(url, prefer_chrome=open_target != "기본 브라우저")


def add_version(png: bytes, note: str) -> None:
    ss.versions.append({"png": png, "note": note})
    bridge.save_output(OUT_DIR, png, len(ss.versions))


def import_result(note: str) -> None:
    if b := clipboard_or_warn():
        add_version(b, note)
        st.toast(f"v{len(ss.versions)}로 가져왔어요.")
        st.rerun()


# ================================================================ UI
st.title("🏛️ 건축 다이어그램 에이전트")

# ---------------------------------------------------------------- ① 어떤 다이어그램
st.subheader("① 어떤 다이어그램인가요?  (가장 우선)")
st.pills("유형 (여러 개 선택 가능)", DIAGRAM_TYPES, selection_mode="multi", key="diagram_types")
st.text_area(
    "무엇을 보여주는 다이어그램인지",
    key="diagram_goal",
    height=80,
    placeholder="예: 대지 경사를 따라 매스가 3단계로 쪼개지며 중정이 생기는 과정. 1층은 공용, 2~3층은 주거.",
)

c1, c2 = st.columns(2)

# ---------------------------------------------------------------- ② 분위기 · 레퍼런스
with c1:
    st.subheader("② 분위기 · 레퍼런스")
    refs = st.file_uploader("레퍼런스 이미지 (여러 장, 선택)", type=["png", "jpg", "jpeg", "webp"],
                            accept_multiple_files=True)
    pa, pb = st.columns(2)
    if pa.button("📋 레퍼런스 붙여넣기", help="복사한 이미지를 레퍼런스로 추가 (핀터레스트, 웹, 포토샵 등)"):
        if b := clipboard_or_warn():
            ss.pasted_refs.append(b)
    if ss.pasted_refs and pb.button("붙인 것 비우기"):
        ss.pasted_refs = []
        st.rerun()
    ref_bytes = ([f.getvalue() for f in refs] if refs else []) + ss.pasted_refs
    if ref_bytes:
        st.image(ref_bytes, width=90)

    ss.mood = st_keyup(
        "원하는 느낌 (문장으로 자유롭게)",
        value=ss.mood,
        key=f"mood_{ss.mood_ver}",
        debounce=900,
        placeholder="예: 따뜻하고 손으로 그린 듯한 느낌, 동선이 한눈에 보였으면",
    ) or ""

    # 구절별 추천: (구절, 직접 대체 그래픽 키워드, 비슷한 느낌의 건축 언어)
    types = list(ss.get("diagram_types") or [])
    rows: list[tuple[str, list[str], list[str]]] = []
    engine = "기본 사전"
    if ss.mood.strip():
        rows = suggest_by_phrase(ss.mood, types)
        if gemini_key and gemini_fast and len(ss.mood.strip()) >= 4:
            try:
                g_rows = gemini_suggest(ss.mood.strip(), goal_text(), gemini_key, gemini_fast, fast_fallbacks)
                # Gemini가 건축 언어를 비워 보내면 사전 추천으로 채움
                rows = [(p, d, sim or suggest_for_phrase(p, types)[1]) for p, d, sim in g_rows] or rows
                engine = "Gemini"
            except Exception as e:  # noqa: BLE001  (한도 초과 등 → 사전으로)
                st.caption(f"Gemini 추천 실패 → 기본 사전 사용 ({str(e)[:80]})")

    def _sync(key: str, opts: list[str]):
        chosen = st.session_state.get(key) or []
        ss.picked = [k for k in ss.picked if k not in opts] + list(chosen)

    def _pills(label: str, opts: list[str], salt: str):
        key = "pk_" + str(abs(hash((salt, tuple(opts)))))
        st.pills(label, opts, selection_mode="multi", key=key,
                 default=[o for o in opts if o in ss.picked], on_change=_sync, args=(key, opts))

    st.caption(f"추천: {engine} — 단어를 클릭하면 선택돼요")
    if not rows:
        _pills("자주 쓰는 키워드", DEFAULT_KEYWORDS, "default")
    for phrase, direct, similar in rows:
        st.markdown(f"**“{phrase}”**")
        if direct:
            _pills("🎨 바로 바꿀 표현", direct, "d" + phrase)
        _pills("🏛️ 비슷한 느낌의 건축 언어", similar, "s" + phrase)

    def _replace(rows_):
        text = ss.mood
        for phrase, direct, similar in rows_:
            chosen = [ko(o) for o in direct + similar if o in ss.picked]
            if chosen and phrase in text:
                text = text.replace(phrase, ", ".join(dict.fromkeys(chosen)), 1)
        ss.mood, ss.mood_ver = text, ss.mood_ver + 1

    k1, k2, k3 = st.columns(3)
    k1.button("↻ 선택한 단어로 문장 바꾸기", on_click=_replace, args=(rows,),
              disabled=not any(o in ss.picked for _, d, sim in rows for o in d + sim))
    if k2.button("선택 초기화"):
        ss.picked = []
        st.rerun()
    if k3.button("스타일 가이드 생성", disabled=not (has_llm and (ref_bytes or ss.mood or ss.picked)),
                 help=None if has_llm else "Gemini 키(무료)나 OpenAI API 키가 있으면 레퍼런스를 분석해요"):
        try:
            with st.spinner("레퍼런스 분석 중..."):
                ss.style_guide = llm.style_guide(ref_bytes, mood_text(), **llm_keys())
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"스타일 분석 실패: {str(e)[:200]}")
    if ss.picked:
        st.caption("선택됨: " + " · ".join(ko(p) for p in ss.picked))
    with st.expander("스타일 가이드 (자동 생성, 직접 수정 가능)", expanded=bool(ss.style_guide)):
        ss.style_guide = st.text_area("style guide", ss.style_guide, height=180, label_visibility="collapsed")

has_input = bool(goal_text() or ref_bytes or ss.mood or ss.picked)

# ---------------------------------------------------------------- ③ 스케치 + 생성
with c2:
    st.subheader("③ 내 스케치")
    t_clip, t_dir, t_file = st.tabs(["📋 클립보드", "📁 폴더", "📄 파일"])
    with t_clip:
        st.caption("**포토샵** Ctrl+Shift+C · **라이노** `ViewCaptureToClipboard` · "
                   "**스케치업/PPT/종이 사진** Win+Shift+S로 캡처 → 아래 버튼")
        if st.button("클립보드 이미지 가져오기"):
            if b := clipboard_or_warn():
                ss.sketch_bytes, ss.sketch_src = b, "클립보드"
    with t_dir:
        files = bridge.latest_images(inbox)
        if files:
            pick = st.selectbox("최근 이미지 (새 파일이 맨 위)", files, format_func=lambda p: p.name)
            d1, d2 = st.columns(2)
            if d1.button("이 파일 사용"):
                ss.sketch_bytes, ss.sketch_src = pick.read_bytes(), pick.name
            if d2.button("🔄 새로고침"):
                st.rerun()
        else:
            st.caption(f"`{inbox}` 폴더에 이미지가 없어요.")
        st.caption("라이노 `ViewCaptureToFile`, 스케치업 `파일 › 내보내기 › 2D 그래픽`으로 이 폴더에 저장하세요.")
        if st.button("폴더 열기"):
            bridge.open_folder(inbox)
    with t_file:
        f = st.file_uploader("손그림 / 거친 디지털 이미지", type=["png", "jpg", "jpeg", "webp"])
        if f and ss.get("upload_id") != f.file_id:
            ss.upload_id = f.file_id
            ss.sketch_bytes, ss.sketch_src = f.getvalue(), f.name

    if ss.sketch_bytes:
        st.image(ss.sketch_bytes, caption=f"현재 스케치 · {ss.sketch_src}", use_container_width=True)

    extra = st.text_input("추가 지시 (선택)", placeholder="예: 동선은 주황 화살표, 라벨은 영어로")
    ready = bool(ss.sketch_bytes and has_input)
    if not ready:
        st.caption("스케치 + (① 다이어그램 설명이나 ② 분위기/레퍼런스 중 하나 이상)이 필요해요.")

    if not use_api:
        st.markdown(f"##### {'Codex로 자동 생성' if use_codex else 'ChatGPT로 생성하기'} · {quality_label} · 생각: {think}")
        draft = chatgpt_prompt(len(ref_bytes), extra) if ready else ""
        if use_codex:
            steps = " → ".join(x for x in ["프롬프트", "" if pipe_engine == "검토 없이" else "Claude 검토",
                                           f"Codex({codex_model}) 생성", "결과 등록"] if x)
            st.caption(f"원클릭 순서: {steps}")
            if st.button("🤖 원클릭 전체 자동 실행", type="primary", disabled=not (ready and codex_status()),
                         use_container_width=True):
                run_pipeline(ref_bytes, extra, draft)
            st.caption("또는 아래에서 단계별로 진행할 수 있어요.")
        if claude_sub:
            if st.button("🔍 Claude에서 프롬프트 검토 (구독)", disabled=not ready):
                send_to_claude(ref_bytes, draft)
            if ss.get("claude_request"):
                img_step = ("입력창 클릭 → **Ctrl+V** (이미지 첨부)" if ss.get("clip_ok")
                            else "`to_chatgpt` 폴더의 이미지를 입력창에 **끌어다 놓기**")
                if ss.get("claude_opened") == "desktop":
                    c_steps = (f"1. Claude 앱에서 {img_step}\n"
                               "2. 이 화면의 **📝 검토 요청 복사** → 앱 입력창에 **Ctrl+V** → **Enter**")
                elif ss.get("claude_prefilled"):
                    c_steps = (f"1. Claude({ss.get('claude_opened')}) 입력창에 **검토 요청이 미리 채워져 있어요**\n"
                               f"2. {img_step} → **Enter**")
                else:
                    c_steps = f"1. {img_step}\n2. **📝 검토 요청 복사** → Ctrl+V → **Enter**"
                st.info("**Claude에서 할 일**\n" + c_steps
                        + "\n3. Claude가 문제점과 **개선 프롬프트** (코드 블록)를 답하면, 코드 블록의 **복사 버튼** 클릭"
                          "\n4. 아래 **📥 Claude 검토본 가져오기**")
                c1_, c2_, c3_ = st.columns(3)
                if c1_.button("📝 검토 요청 복사"):
                    try:
                        bridge.copy_text(ss.claude_request)
                        st.toast("검토 요청을 복사했어요.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"복사 실패: {e}")
                if c2_.button("🖼️ 이미지 다시 복사", key="claude_img_copy"):
                    try:
                        copy_attachments()
                        st.toast("이미지를 복사했어요.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"복사 실패: {e}")
                if c3_.button("📥 Claude 검토본 가져오기"):
                    import_claude_review()
        elif st.button("🔍 Claude로 프롬프트 검토", disabled=not (ready and claude_key),
                       help=None if claude_key else "사이드바에 Claude API 키를 넣으면 쓸 수 있어요"):
            run_review(ref_bytes, draft)
        r = ss.get("review")
        if r:
            if r["draft"] != draft:
                st.warning("검토 후 입력이 바뀌었어요. 지금 보내면 새 초안이 그대로 가요. 다시 검토하려면 위 버튼을 누르세요.")
            with st.container(border=True):
                st.markdown(f"**Claude 검토 결과** · {r.get('model_used', '')}")
                st.write(r["summary_ko"])
                icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}
                for it in r["issues"]:
                    st.markdown(f"{icon.get(it['severity'], '•')} **{it['problem_ko']}** → {it['fix_ko']}")
                if r["sketch_reading_ko"] or r["reference_style_ko"]:
                    with st.expander("Claude가 읽은 스케치 구조 / 레퍼런스 스타일"):
                        st.markdown("**스케치**\n\n" + r["sketch_reading_ko"])
                        st.markdown("**레퍼런스**\n\n" + r["reference_style_ko"])
                with st.expander("개선된 프롬프트 (직접 수정 가능)", expanded=False):
                    st.text_area("improved", key="reviewed_text", height=320, label_visibility="collapsed")
                st.checkbox("✅ 검토된 프롬프트로 보내기", key="use_reviewed", value=True,
                            disabled=r["draft"] != draft)
        if use_codex:
            if st.button(f"⚡ 현재 프롬프트로 Codex 생성 ({codex_model})",
                         disabled=not (ready and codex_status())):
                codex_generate(ref_bytes, extra)
            if ss.get("gpt_prompt"):
                with st.expander("보낸 프롬프트 보기"):
                    st.code(ss.gpt_prompt, language=None, wrap_lines=True)
        elif st.button("🚀 ChatGPT로 보내기", type="primary", disabled=not ready):
            send_to_chatgpt(ref_bytes, extra)
        if use_chatgpt and ss.get("gpt_prompt"):
            img_step = ("입력창을 클릭하고 **Ctrl+V** → 이미지가 첨부돼요" if ss.get("clip_ok")
                        else "`to_chatgpt` 폴더의 이미지를 입력창에 **끌어다 놓기**")
            if ss.get("opened") == "desktop":
                steps = (f"1. ChatGPT 앱에서 {img_step}\n"
                         "2. 이 화면의 **📝 프롬프트 복사** → 앱 입력창에 **Ctrl+V** → **Enter**")
            elif ss.get("prefilled"):
                steps = (f"1. ChatGPT({ss.get('opened')}) 입력창에 **프롬프트가 미리 채워져 있어요**\n"
                         f"2. {img_step}\n"
                         "3. **Enter**\n\n"
                         "프롬프트가 안 채워졌으면 → **📝 프롬프트 복사** → Ctrl+V → **🖼️ 이미지 다시 복사** → Ctrl+V → Enter")
            else:
                steps = (f"1. {img_step}\n2. **📝 프롬프트 복사** → Ctrl+V → **Enter**")
            tips = []
            if think == "깊게 생각":
                tips.append("ChatGPT 상단 모델 메뉴에서 **Thinking** 모델을 고르면 더 확실해요.")
            if attach_mode == "파일 여러 장":
                tips.append("Ctrl+V로 이미지가 안 붙으면 사이드바 **이미지 첨부 방식 → 한 장으로 합치기**로 바꿔 다시 보내세요.")
            st.info("**ChatGPT에서 할 일**\n" + steps
                    + ("\n\n" + "\n\n".join(tips) if tips else "")
                    + "\n\n**결과가 마음에 들면** 이미지 우클릭 → *이미지 복사* → **📥 결과 가져오기**")
            b1, b2, b3 = st.columns(3)
            if b1.button("📝 프롬프트 복사"):
                try:
                    bridge.copy_text(ss.gpt_prompt)
                    st.toast("프롬프트를 복사했어요.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"복사 실패: {e}")
            if b2.button("🖼️ 이미지 다시 복사"):
                try:
                    copy_attachments()
                    st.toast("이미지를 복사했어요.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"복사 실패: {e}")
            if b3.button("📥 결과 가져오기"):
                import_result("ChatGPT 결과")
            with st.expander("프롬프트 보기"):
                st.code(ss.gpt_prompt, language=None, wrap_lines=True)
    elif st.button(f"✨ 다이어그램 생성 · {quality_label}", type="primary", disabled=not (ready and api_key)):
        with st.spinner("다이어그램 생성 중... (30초~1분)"):
            png = render(ss.sketch_bytes, ref_bytes, "Redraw IMAGE 1 as a finished diagram. " + extra)
        add_version(png, "초기 생성")
        ss.chat.append(("assistant", f"v{len(ss.versions)} 생성 완료. 수정할 점을 채팅으로 알려주세요."))

# ---------------------------------------------------------------- ④ 결과
if ss.versions:
    st.divider()
    st.subheader("④ 결과 & 수정")
    left, right = st.columns([3, 2])
    with left:
        idx = (st.select_slider("버전", options=list(range(len(ss.versions))), value=len(ss.versions) - 1,
                                format_func=lambda i: f"v{i + 1}")
               if len(ss.versions) > 1 else 0)
        v = ss.versions[idx]
        st.image(v["png"], caption=f"v{idx + 1} · {v['note']}", use_container_width=True)
        e1, e2, e3, e4 = st.columns(4)
        if e1.button("📋 복사", help="포토샵·PPT에 Ctrl+V로 바로 붙여넣기"):
            try:
                bridge.copy_to_clipboard(v["png"])
                st.toast("클립보드에 복사했어요. Ctrl+V 하세요.")
            except Exception as e:  # noqa: BLE001
                st.error(f"복사 실패: {e}")
        e2.download_button("PNG 저장", v["png"], f"diagram_v{idx + 1}.png", "image/png")
        e3.download_button(
            "PPT (전체 버전)",
            bridge.build_pptx([(x["png"], f"v{i + 1} · {x['note']}") for i, x in enumerate(ss.versions)]),
            "diagrams.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        if e4.button("결과 폴더"):
            bridge.open_folder(OUT_DIR)
    with right:
        if use_chatgpt:
            st.markdown("**수정은 ChatGPT에서** 이어서 요청하고, 새 결과가 나올 때마다 가져오세요.")
            note = st.text_input("메모 (선택)", placeholder="예: 매스 반투명 처리")
            if st.button("📥 새 버전 가져오기 (클립보드)"):
                import_result(note or "ChatGPT 수정본")
        else:
            for role, text in ss.chat:
                st.chat_message(role).write(text)
            req = st.chat_input("수정 요청 (예: 2층 매스를 더 투명하게, 라벨 폰트 작게)")
            if req:
                ss.chat.append(("user", req))
                if use_codex:
                    if codex_revise(v["png"], idx, req, ref_bytes):
                        st.rerun()
                else:
                    with st.spinner(f"v{idx + 1} 기준으로 수정 중..."):
                        png = render(v["png"], ref_bytes,
                                     f"Keep everything from IMAGE 1 unchanged except this revision: {req}")
                    add_version(png, req)
                    ss.chat.append(("assistant", f"v{len(ss.versions)} 완료 (v{idx + 1} 기반)."))
                    st.rerun()
