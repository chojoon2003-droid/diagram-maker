"""
건축 다이어그램 에이전트 (프로토타입)

우선순위:  ① 어떤 다이어그램인지  >  ② 스케치 구조  >  ③ 분위기·레퍼런스 스타일
 - 분위기 문장을 쓰면 구절마다 '대체 키워드'를 실시간 추천 (Gemini 무료 / 기본 사전)
 - 생성: ChatGPT 구독 모드(프롬프트+이미지 준비 → ChatGPT) 또는 API 모드(앱에서 바로)
 - 결과: 클립보드 복사 / outputs 자동 저장 / PPT 내보내기
"""

import base64
import io
import json
import os
import re
from urllib.parse import urlencode
from pathlib import Path

import streamlit as st
from PIL import Image
from st_keyup import st_keyup

import io_bridge as bridge
import cad_import
import claude_cli
import claude_review
import drawing_tools
import codex_bridge
import llm
import prompts
from keywords import DEFAULTS_BY_WORK, ko, suggest_by_phrase, suggest_for_phrase

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
PRESET_DIR = APP_DIR / "presets"
DEFAULT_INBOX.mkdir(exist_ok=True)

PLAN_TYPES = ["실별 색 구분", "가구·인테리어", "조경·외부공간", "바닥 재질", "그림자·깊이감", "흑백 포셰 강조", "동선 표시"]
RENDER_TYPES = ["주간 (맑음)", "골든아워", "야경", "흐림·비", "계절감", "눈높이 컷", "조감 컷", "디테일 컷", "첨경 많이", "첨경 적게"]
SECTION_TYPES = ["절단면 포셰 강조", "지반·지형", "빛·환경 흐름", "사람·스케일", "단면 투시(깊이감)", "재료·구조", "배경·하늘"]
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

st.title("🏛️ 건축 다이어그램 에이전트")
work_type = st.radio("작업 종류", prompts.WORK_TYPES, horizontal=True, key="work_type",
                     help="다이어그램: 스케치를 다이어그램으로\n\n평면·단면 리터칭: 내 도면의 선은 그대로 두고 색·질감·그림자·첨경을 입혀요")
is_drawing = work_type != "다이어그램"  # 다이어그램이 아닌 모든 작업 (평면·단면·렌더링)
is_render = work_type == "렌더링"
is_retouch = work_type in ("평면 리터칭", "단면 리터칭")
INPUT_LABEL = {"다이어그램": "내 스케치", "평면 리터칭": "리터칭할 도면", "단면 리터칭": "리터칭할 도면", "렌더링": "렌더링할 모델 뷰"}

ss = st.session_state
for k, v in {
    "style_guide": "", "versions": [], "chat": [], "picked": [], "pasted_refs": [],
    "sketch_bytes": None, "sketch_src": None, "mood": "", "mood_ver": 0,
    "pasted_projects": [], "project_text": "", "cad_items": {},
    "anchor": None, "material_map": None, "material_legend": [], "materials": "",
}.items():
    ss.setdefault(k, v)


def _read(p: Path) -> str:
    return p.read_text().strip() if p.exists() else ""


@st.cache_data(ttl=3600, show_spinner="Codex·Claude Code 연결 상태 확인 중...")
def tool_status() -> dict:
    """Codex·Claude Code 설치/로그인 확인 4가지를 동시에 실행 (순서대로 하면 윈도우에서 수 초~십수 초)."""
    from concurrent.futures import ThreadPoolExecutor

    jobs = {"codex": codex_bridge.codex_version, "codex_login": codex_bridge.login_status,
            "claude": claude_cli.claude_version, "claude_login": claude_cli.login_status}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(f) for k, f in jobs.items()}
    return {k: f.result() for k, f in futs.items()}


def claude_login_status() -> str:
    return tool_status()["claude_login"]


def claude_code_status() -> str:
    return tool_status()["claude"]


def codex_login_status() -> str:
    return tool_status()["codex_login"]


def codex_status() -> str:
    return tool_status()["codex"]


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def gemini_models(key: str) -> list[str]:
    return llm.list_gemini_models(key)


# ---------------------------------------------------------------- 설정
with st.sidebar:
    st.header("설정")
    with st.expander("💾 프로젝트 프리셋 (같은 프로젝트 여러 컷을 같은 톤으로)"):
        PRESET_KEYS = (["materials", "material_legend", "diagram_goal", "mood", "picked", "detail", "style_strength",
                        "project_text", "facts_strict"] + [f"types_{w}" for w in prompts.WORK_TYPES])
        PRESET_DIR.mkdir(exist_ok=True)
        names = sorted(p.stem for p in PRESET_DIR.glob("*.json"))
        sel = st.selectbox("불러오기", ["(선택)"] + names, key="preset_sel")
        if st.button("불러오기", disabled=sel == "(선택)"):
            data = json.loads((PRESET_DIR / f"{sel}.json").read_text(encoding="utf-8"))
            for k in PRESET_KEYS:
                if k in data:
                    ss[k] = data[k]
            ss.mood_ver += 1
            for k in ("anchor_png", "material_map"):
                if data.get(k):
                    b = base64.b64decode(data[k])
                    if k == "anchor_png":
                        ss.anchor = {"png": b, "note": data.get("anchor_note", "프리셋 기준 컷")}
                    else:
                        ss.material_map = b
            st.rerun()
        pname = st.text_input("현재 설정을 저장할 이름", placeholder="예: OO복합시설_외관")
        if st.button("저장", disabled=not pname.strip()):
            data = {k: ss.get(k) for k in PRESET_KEYS if k in ss}
            if ss.anchor:
                data["anchor_png"] = base64.b64encode(ss.anchor["png"]).decode()
                data["anchor_note"] = ss.anchor["note"]
            if ss.material_map:
                data["material_map"] = base64.b64encode(ss.material_map).decode()
            (PRESET_DIR / f"{pname.strip()}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            st.success("저장했어요. 다른 날·다른 컷에서 불러오면 재료·느낌·키워드·기준 컷이 그대로 돌아와요.")
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
                tool_status.clear()
                st.rerun()
        else:
            st.warning(codex_bridge.SETUP_HELP)
        codex_model = st.text_input("Codex 모델", "gpt-6-astra",
                                    help="Codex에서 쓸 모델 이름. 예: gpt-6-astra. 이미지는 Codex 내장 이미지 생성으로 만들어요.")
        think = st.select_slider("생각 수준", options=["빠르게", "자동", "깊게 생각"], value="빠르게",
                                 help="Codex 추론 강도 (low / medium / high). 검수는 Claude가 따로 하니 "
                                      "'빠르게'면 충분해요 — 높일수록 OpenAI 사용량이 늘어요.")
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
                    tool_status.clear()
                    st.rerun()
            else:
                st.warning(claude_cli.SETUP_HELP)
            cc_model = st.selectbox("Claude Code 모델", list(claude_cli.MODELS))
    if use_chatgpt:
        open_target = st.radio("ChatGPT 여는 곳", ["Chrome", "ChatGPT 데스크탑 앱", "기본 브라우저"],
                               help="Chrome/브라우저: 입력창에 프롬프트를 미리 채워서 열어요.\n\n"
                                    "데스크탑 앱: 앱을 열고, 프롬프트는 버튼으로 복사해 붙여넣어요.")
        think = st.select_slider("ChatGPT 생각 수준", options=["빠르게", "자동", "깊게 생각"], value="빠르게",
                                 help="프롬프트에 생각 깊이 지시를 넣어요. 확실하게 하려면 ChatGPT 화면 상단 "
                                      "모델 메뉴에서도 같은 수준(예: Thinking)을 골라주세요.")
        attach_mode = st.radio("이미지 첨부 방식", ["파일 여러 장", "한 장으로 합치기"],
                               help="파일 여러 장: 스케치·레퍼런스를 각각 첨부 (화질 좋음)\n\n"
                                    "한 장으로 합치기: 붙여넣기가 잘 안 될 때. 스케치+레퍼런스를 라벨 붙인 보드 1장으로")
        prompt_lang = st.radio("프롬프트 언어", ["English (추천)", "한국어"], horizontal=True,
                               help="AI는 영어 지시를 더 정확히 따르는 편이에요. ChatGPT 답변은 한국어로 오게 해뒀어요.")
    notify_on = st.checkbox("🔔 완료 알림 (다른 작업 중에도 알림)", value=True,
                            help="이미지가 완성되고 Claude 검수가 끝나면 화면 오른쪽 아래에 알림과 소리가 나요. "
                                 "생성이 실패해도 알려줘요.")
    quality_label = st.select_slider("화질", options=list(QUALITY), value="표준")
    aspect = st.selectbox("비율", list(ASPECT), index=1)
    form_label = st.select_slider(
        "형태 변형 단계", options=prompts.FORM_LABELS,
        value=prompts.FORM_LABELS[0 if is_drawing else 1], key=f"form_{work_type}",
        help="\n\n".join(f"{lab}: {h}" for lab, h in zip(prompts.FORM_LABELS, prompts.FORM_HELP)),
    )
    form_level = prompts.FORM_LABELS.index(form_label)
    st.caption(prompts.FORM_HELP[form_level])
    line_lock = st.checkbox("📐 원본 선 고정 합성", value=is_retouch, key=f"lock_{work_type}",
                            help="AI 결과 위에 원본 도면/스케치의 선을 다시 겹쳐서, AI가 선을 틀어도 최종본의 선은 원본과 같게 해요. "
                                 "AI 원본과 선 고정본이 둘 다 결과 목록에 추가돼요.")
    multipass, pass_qa = False, False
    if is_render:
        multipass = st.checkbox("🪜 나눠서 렌더링 (재료·조명 → 하늘·배경 → 첨경)", value=False,
                                disabled=use_chatgpt,
                                help="한 번에 다 그리지 않고 3번에 나눠 그려서 건물 형태가 덜 틀어져요. "
                                     "대신 생성 횟수가 3배라 OpenAI 사용량이 늘어요. (Codex·API 모드)")
        if multipass:
            pass_qa = st.checkbox("단계마다 Claude 검수", value=False, help="끄면 마지막 단계만 검수해요 (사용량 절약)")
    lock_opacity, lock_threshold = 1.0, 150
    if line_lock:
        lock_opacity = st.slider("선 진하기", 0.3, 1.0, 1.0, 0.05, help="1.0이면 원본 선을 그대로, 낮추면 AI 표현과 섞여요")
        lock_threshold = st.slider("선 인식 감도", 80, 220, 150, 10,
                                   help="높일수록 옅은 선(해치·가는 선)까지 원본에서 가져와요. 회색 바탕이 덮이면 낮추세요.")
    detail = st.select_slider(
        "첨경·디테일 수준", options=prompts.DETAIL_LEVELS, key="detail",
        **({} if "detail" in ss else {"value": prompts.DETAIL_LEVELS[1]}),
        help="단순: 실루엣·단순 형태\n\n사실적 (과한 디테일 없이): 비례·자세는 사실적, 옷 재질·얼굴·잎 하나하나 같은 세부 묘사 없음\n\n"
             "풍부: 질감·디테일 허용 (OpenAI 처리량이 늘 수 있어요)",
    )
    style_strength = st.select_slider(
        "레퍼런스 스타일 강도", options=["구조 우선", "균형", "스타일 우선"], key="style_strength",
        **({} if "style_strength" in ss else {"value": "균형"}),
        help="구조 우선: 레퍼런스는 느슨한 참고\n\n균형: 색·선·라벨·화살표를 가깝게 따름\n\n"
             "스타일 우선: 레퍼런스의 그래픽 언어만 사용, 레퍼런스에 없는 제목·범례 등은 추가 금지 (형태는 스케치 유지)",
    )

    st.divider()
    st.subheader("프롬프트 검토 (Claude)")
    auto_qa = st.checkbox("🔎 이미지 생성 후 자동 Claude 검수", value=True,
                          help="새 이미지가 나오면 Claude가 스케치·레퍼런스·설명과 비교해 검수해요. "
                               "문제가 있으면 수정 프롬프트와 '다시 생성' 버튼이 나와요. "
                               "(Claude Code 로그인 또는 Claude API 키 필요)")
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
    if current_types():
        parts.append(("유형: " if not is_drawing else "리터칭 초점: ") + ", ".join(current_types()))
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
        types=current_types(), goal=ss.get("diagram_goal", ""), mood=ss.mood,
        keywords=list(ss.picked), style_guide=ss.style_guide, strict=form_level <= 1,
        quality=quality_label, aspect=aspect, think=think, extra=extra, style_strength=style_strength,
        project_text=ss.get("project_text", ""), n_project=len(project_bytes),
        facts_strict=ss.get("facts_strict", True), work_type=work_type, form_level=form_level, detail=detail,
        materials=ss.materials if is_render else "", material_legend=ss.material_legend if is_render else [],
        has_material_map=bool(is_render and ss.material_map), has_anchor=anchor_on(),
    )


def anchor_on() -> bool:
    return bool(ss.anchor and ss.get("use_anchor", True))


def map_on() -> bool:
    return bool(is_render and ss.material_map)


def current_types() -> list[str]:
    return list(ss.get(f"types_{work_type}") or [])


def project_items() -> list[tuple[str, bytes]]:
    return [(f"3_project_{i + 1}.png", b) for i, b in enumerate(project_bytes)]


def attach_items(ref_bytes: list[bytes]) -> list[tuple[str, bytes]]:
    """첨부 순서: 스케치 → 레퍼런스 → 내 설계 도면"""
    return ([("1_sketch.png", ss.sketch_bytes)] + [(f"2_reference_{i + 1}.png", b) for i, b in enumerate(ref_bytes)]
            + project_items() + ([("4_material_map.png", ss.material_map)] if map_on() else []))


# ---------------------------------------------------------------- API 모드 생성
def render(base_png: bytes, ref_bytes: list[bytes], instruction: str) -> bytes:
    prompt = prompts.image_api(spec(), len(ref_bytes), instruction)
    files = ([to_png_file(base_png, "base.png")] + [to_png_file(b, f"ref{i}.png") for i, b in enumerate(ref_bytes)]
             + [to_png_file(b, f"project{i}.png") for i, b in enumerate(project_bytes)])
    kwargs = dict(model=image_model, image=files, prompt=prompt,
                  size=ASPECT[aspect], quality=QUALITY[quality_label][0])
    from openai import OpenAI  # 필요할 때만 불러와서 앱 시작을 빠르게

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
        f"- 작업 종류: {work_type} / 유형·초점: {', '.join(current_types()) or '미지정'}",
        f"- 다이어그램 설명: {ss.get('diagram_goal') or '없음'}",
        f"- 원하는 느낌: {ss.mood or '없음'}",
        f"- 선택 키워드: {', '.join(ss.picked) or '없음'}",
        f"- 형태 변형 단계: {form_label} ({form_level + 1}/5) — {prompts.FORM_HELP[form_level]}",
        f"- 레퍼런스 스타일 강도: {style_strength} / 원본 선 고정 합성: {'켜짐' if line_lock else '꺼짐'}",
        f"- 첨경·디테일 수준: {detail} — {prompts.DETAIL_KO[detail]}",
        f"- 기준 컷(같은 프로젝트 확정 컷)을 마지막 레퍼런스로 사용: {'예' if anchor_on() else '아니오'}",
    ] + ([f"- 재료 지정:\n{ss.materials.strip()}"] if is_render and ss.materials.strip() else []) + (
        [f"- 재료 색 코딩 맵 범례: " + "; ".join(f"{h}={m}" for h, m in ss.material_legend if m.strip())]
        if map_on() else []) + [
        f"- 이미지 첨부 방식: {attach_mode} / 화질: {quality_label} / 비율: {aspect} / 생각 수준: {think}",
        f"- 내 설계 자료: 도면 {len(project_bytes)}장, 설계 글 {'있음' if ss.get('project_text', '').strip() else '없음'}"
        f" / 없는 내용 추가 금지: {'예' if ss.get('facts_strict', True) else '아니오'}",
    ] + ([f"- 프로그램·설계 논리 (내 글):\n{ss.project_text.strip()[:3000]}"] if ss.get("project_text", "").strip() else []))


def map_extra_bytes() -> list[tuple[bytes, str]]:
    return [(ss.material_map, "MATERIAL ID MAP (same camera; flat colors = materials)")] if map_on() else []


def map_extra_files() -> list[tuple[str, str]]:
    return [("4_material_map.png", "MATERIAL ID MAP (same camera; flat colors = materials)")] if map_on() else []


def run_review(ref_bytes: list[bytes], draft: str) -> None:
    model = claude_review.MODELS[claude_model_label]
    try:
        with st.spinner(f"Claude({claude_model_label})가 스케치·레퍼런스를 보며 검토 중... (30초~2분)"):
            result = claude_review.review(claude_key, model, claude_effort, draft, review_context(),
                                          ss.sketch_bytes, ref_bytes, project_bytes, map_extra_bytes())
        ss.review = {"draft": draft, **result}
        ss.reviewed_text = result["improved_prompt"]
    except RuntimeError as e:
        st.error(str(e))


def prepare_attachments(ref_bytes: list[bytes]) -> None:
    """to_chatgpt 폴더에 첨부 이미지를 만들고 클립보드에 복사 (ChatGPT·Claude 공용)."""
    bridge.write_images(TO_GPT_DIR, attach_items(ref_bytes))
    if attach_mode == "한 장으로 합치기":
        (TO_GPT_DIR / "board.png").write_bytes(bridge.make_board(
            ss.sketch_bytes, ref_bytes, project_bytes, [(ss.material_map, "MATERIAL MAP")] if map_on() else None))
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
                                            attach_mode == "한 장으로 합치기", n_project=len(project_bytes),
                                            has_map=map_on())
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


def _codex_call(prompt: str, images: list[str], note: str, session: str | None, qa: bool = True) -> bool:
    out = f"result_v{len(ss.versions) + 1}.png"
    try:
        with st.spinner(f"Codex({codex_model})가 생성 중이에요... 보통 1~5분 걸려요. 이 창을 닫지 마세요."):
            res = codex_bridge.run(CODEX_DIR, prompt, images, out, codex_model,
                                   codex_bridge.EFFORT[think], session_id=session)
    except RuntimeError as e:
        st.error(str(e).split("\n\n")[0])
        if notify_on:
            bridge.notify("❌ 다이어그램 생성 실패", str(e).split("\n")[0][:120])
        detail = str(e).split("\n\n", 1)
        if len(detail) > 1:
            with st.expander("Codex 실행 기록"):
                st.code(detail[1], language=None)
        return False
    ss.codex_session, ss.codex_log = res["session_id"], res["log"]
    ss.chat.append(("assistant", f"v{len(ss.versions) + 1} 완료 ({note})."))
    register_result(res["png"], note, prompt=prompt, qa=qa)
    return True


def codex_generate(ref_bytes: list[bytes], extra: str) -> None:
    prompt = final_prompt(chatgpt_prompt(len(ref_bytes), extra))
    ss.gpt_prompt = prompt
    items = attach_items(ref_bytes)
    bridge.write_images(CODEX_DIR, items)
    if multipass:
        codex_passes(prompt, [n for n, _ in items], "Codex 생성")
    else:
        _codex_call(prompt, [n for n, _ in items], "Codex 생성", None)


def codex_passes(prompt: str, images: list[str], note: str) -> bool:
    """렌더링 3단계 생성: 재료·조명 → 하늘·배경 → 첨경. 단계마다 결과가 목록에 추가돼요."""
    refs = [n for n in images if n.startswith("2_")]
    for k, (instr, pname) in enumerate(zip(prompts.PASSES_EN, prompts.PASS_NAMES)):
        last = k == len(prompts.PASSES_EN) - 1
        st.write(f"🪜 {pname} 생성 중...")
        if k == 0:
            ok = _codex_call(f"{prompt}\n\n{instr}", images, f"{note} · {pname}", None, qa=last or pass_qa)
        else:
            base = f"pass_{k}.png"
            (CODEX_DIR / base).write_bytes(ss.versions[-1]["png"])
            p2 = (f"{instr}\nAttached: `{base}` = the current image to edit; `1_sketch.png` = the model view "
                  "(geometry and camera reference)" + (f"; {', '.join(refs)} = style references" if refs else "")
                  + f".\n{prompts.DETAIL_EN[detail]}\n{prompts.EFFICIENCY_EN}")
            ok = _codex_call(p2, [base, "1_sketch.png", *refs], f"{note} · {pname}", ss.get("codex_session"),
                             qa=last or pass_qa)
        if not ok:
            return False
    return True


def run_pipeline(ref_bytes: list[bytes], extra: str, draft: str) -> None:
    """원클릭: 초안 → Claude 검토 → Codex(Astra) 이미지 생성 → 결과 등록."""
    refs = [f"2_reference_{i + 1}.png" for i in range(len(ref_bytes))]
    projs = [n for n, _ in project_items()]
    bridge.write_images(CODEX_DIR, attach_items(ref_bytes))
    prompt = draft
    with st.status("🤖 전체 자동 진행 중...", expanded=True) as status:
        st.write("✅ ① 프롬프트 초안 작성 완료")
        if pipe_engine != "검토 없이":
            st.write(f"⏳ ② Claude 검토 중 ({pipe_engine})... 1~3분")
            try:
                if pipe_engine.startswith("Claude Code"):
                    res = claude_cli.review(CODEX_DIR, draft, review_context(), "1_sketch.png", refs,
                                            claude_cli.MODELS[cc_model], projects=projs, extras=map_extra_files())
                    ss.review = {"draft": draft, "summary_ko": res["summary_ko"], "issues": [],
                                 "sketch_reading_ko": "", "reference_style_ko": "",
                                 "improved_prompt": res["improved_prompt"], "model_used": "Claude Code (구독)"}
                else:
                    key = claude_key or os.getenv("ANTHROPIC_API_KEY", "") or _read(CLAUDE_KEY_FILE)
                    if not key:
                        raise RuntimeError("Claude API 키가 없어요. 사이드바 '프롬프트 검토'에서 키를 넣어주세요.")
                    result = claude_review.review(key, claude_review.MODELS[claude_model_label], claude_effort,
                                                  draft, review_context(), ss.sketch_bytes, ref_bytes, project_bytes,
                                                  map_extra_bytes())
                    ss.review = {"draft": draft, **result}
                ss.reviewed_text = ss.review["improved_prompt"]
                prompt = ensure_rules(ss.reviewed_text)
                st.write("✅ ② Claude 검토 완료 — 검토된 프롬프트로 진행해요")
            except RuntimeError as e:
                st.write(f"⚠️ ② Claude 검토 실패 → 초안 그대로 진행: {str(e).splitlines()[0]}")
        ss.gpt_prompt = prompt
        st.write(f"⏳ ③ Codex({codex_model})로 다이어그램 생성 중... 보통 1~5분")
        imgs = ["1_sketch.png", *refs, *projs] + (["4_material_map.png"] if map_on() else [])
        ok = (codex_passes(prompt, imgs, "원클릭 자동 생성") if multipass
              else _codex_call(prompt, imgs, "원클릭 자동 생성", None))
        if ok:
            st.write("✅ ③ 이미지 생성 완료 → 아래 ④ 결과에 v" + str(len(ss.versions)) + "로 등록")
        status.update(label="🤖 완료! 아래 ④ 결과를 확인하세요" if ok else "🤖 이미지 생성 단계에서 멈췄어요",
                      state="complete" if ok else "error")


def codex_revise(base_png: bytes, idx: int, req: str, ref_bytes: list[bytes]) -> bool:
    base = f"base_v{idx + 1}.png"
    CODEX_DIR.mkdir(exist_ok=True)
    (CODEX_DIR / base).write_bytes(base_png)
    refs, projs = _write_work_files()
    prompt = (f"Revise the attached diagram `{base}` (version v{idx + 1}). Keep everything in it unchanged except "
              f"this revision: {req}\n"
              + (f"The attached {', '.join(refs)} are the style references; keep following them.\n" if refs else "")
              + (f"The attached {', '.join(projs)} are my design drawings: keep the content consistent with them; "
                 "do not invent programs, labels or numbers.\n" if projs else "")
              + f"{prompts.DETAIL_EN[detail]}\n{prompts.EFFICIENCY_EN}")
    return _codex_call(prompt, [base, *refs, *projs], req, ss.get("codex_session"))


def ensure_rules(prompt: str) -> str:
    """Claude 검토본이 '생성만 하기'·디테일 규칙을 빠뜨렸으면 다시 붙인다 (OpenAI 토큰 절약)."""
    if "WORK EFFICIENTLY" not in prompt and "효율적으로" not in prompt:
        prompt += "\n\n" + (prompts.EFFICIENCY_KO if prompt_lang == "한국어" else prompts.EFFICIENCY_EN)
    if "Detail level" not in prompt and "디테일" not in prompt:
        prompt += "\n" + (prompts.DETAIL_KO[detail] if prompt_lang == "한국어" else prompts.DETAIL_EN[detail])
    return prompt


def final_prompt(draft: str) -> str:
    """검토 결과가 지금 초안 기준이고 '검토본 사용'이 켜져 있으면 검토본, 아니면 초안."""
    r = ss.get("review")
    if r and r["draft"] == draft and ss.get("use_reviewed", True) and ss.get("reviewed_text"):
        return ensure_rules(ss.reviewed_text)
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


def register_result(png: bytes, note: str, prompt: str = "", qa: bool = True) -> None:
    """AI가 만든 새 이미지를 등록. 선 고정 합성이 켜져 있으면 'AI 원본'과 '원본 선 고정본'을 둘 다 추가."""
    if line_lock and ss.get("sketch_bytes"):
        add_version(png, f"{note} · AI 원본", prompt, qa=False, notify=False)
        locked, how = drawing_tools.lock_lines(png, ss.sketch_bytes, lock_opacity, lock_threshold)
        add_version(locked, f"{note} · 원본 선 고정 ({how})", prompt, qa=qa)
    else:
        add_version(png, note, prompt, qa=qa)


def compute_diff(v: dict) -> None:
    """렌더링: 입력 모델 뷰와 결과의 윤곽선 비교 (빨강=사라진 윤곽, 파랑=새 윤곽)"""
    try:
        png, pct, how = drawing_tools.edge_diff(ss.sketch_bytes, v["png"])
        v["diff"] = {"png": png, "pct": pct, "how": how}
    except Exception as e:  # noqa: BLE001
        v["diff"] = {"png": None, "pct": None, "how": f"비교 실패: {str(e)[:80]}"}


def add_version(png: bytes, note: str, prompt: str = "", qa: bool = True, notify: bool = True) -> None:
    """새 버전을 목록 맨 아래에 추가 (기존 버전은 그대로). 자동 검수가 켜져 있으면 바로 Claude 검수."""
    ss.versions.append({"png": png, "note": note, "prompt": prompt or ss.get("gpt_prompt", ""), "qa": None})
    saved = bridge.save_output(OUT_DIR, png, len(ss.versions))
    n = len(ss.versions)
    if is_render and ss.get("sketch_bytes"):
        compute_diff(ss.versions[-1])
    if qa and auto_qa and qa_engine()[0] and ss.get("sketch_bytes"):
        run_qa(n - 1)
    if notify and notify_on:
        qa = ss.versions[-1].get("qa")
        if not qa:
            title, body = f"🖼️ v{n} 완성", note
        elif qa["verdict"] == "revise":
            first = [ln.strip() for ln in qa["issues_ko"].splitlines() if ln.strip()][:2]
            title, body = f"⚠️ v{n} 완성 · Claude 검수: 수정 필요", " / ".join(first) or note
        else:
            title, body = f"✅ v{n} 완성 · Claude 검수 통과", note
        bridge.notify(title, body + "\n건축 다이어그램 에이전트에서 확인하세요.", saved)


# ---------------------------------------------------------------- 결과 검수 (Claude)
def qa_engine() -> tuple[str | None, str | None]:
    """('code', None) = Claude Code 구독 / ('api', 키) / (None, None) = 사용 불가"""
    key = claude_key or os.getenv("ANTHROPIC_API_KEY", "") or _read(CLAUDE_KEY_FILE)
    prefer_api = (use_codex and pipe_engine == "Claude API") or (not claude_sub and bool(claude_key))
    if prefer_api and key:
        return "api", key
    if claude_code_status():
        return "code", None
    return ("api", key) if key else (None, None)


def _write_work_files() -> tuple[list[str], list[str]]:
    """검수·재생성용으로 스케치/레퍼런스/내 설계 도면을 작업 폴더에 새로 씀. (레퍼런스, 설계 도면) 파일명 반환."""
    CODEX_DIR.mkdir(exist_ok=True)
    Image.open(io.BytesIO(ss.sketch_bytes)).convert("RGB").save(CODEX_DIR / "1_sketch.png", format="PNG")
    refs, projs = [], []
    for name, b in attach_items(ref_bytes)[1:]:
        if name.startswith("2_"):
            refs.append(name)
        elif name.startswith("3_"):
            projs.append(name)
        Image.open(io.BytesIO(b)).convert("RGB").save(CODEX_DIR / name, format="PNG")
    return refs, projs


def run_qa(i: int) -> bool:
    engine, key = qa_engine()
    if not engine:
        st.warning("검수하려면 Claude Code 로그인(구독) 또는 Claude API 키가 필요해요.")
        return False
    v = ss.versions[i]
    refs, projs = _write_work_files()
    result_name = f"check_v{i + 1}.png"
    (CODEX_DIR / result_name).write_bytes(v["png"])
    extra_files, extra_bytes = list(map_extra_files()), list(map_extra_bytes())
    if (v.get("diff") or {}).get("png"):
        label = ("DIFF MAP (red = model edges missing in the result, blue = new edges; "
                 f"{v['diff']['pct']}% of model edges missing)")
        (CODEX_DIR / f"diff_v{i + 1}.png").write_bytes(v["diff"]["png"])
        extra_files.append((f"diff_v{i + 1}.png", label))
        extra_bytes.append((v["diff"]["png"], label))
    try:
        with st.spinner(f"Claude가 v{i + 1}을(를) 검수하고 있어요... 보통 1~3분"):
            if engine == "code":
                res = claude_cli.qa(CODEX_DIR, result_name, "1_sketch.png", refs, review_context(),
                                    v.get("prompt", ""), claude_cli.MODELS[cc_model], projects=projs,
                                    extras=extra_files)
            else:
                res = claude_review.qa(key, claude_review.MODELS[claude_model_label], claude_effort, v["png"],
                                       ss.sketch_bytes, ref_bytes, review_context(), v.get("prompt", ""),
                                       project_bytes, extra_bytes)
    except RuntimeError as e:
        st.error(f"v{i + 1} 검수 실패: {str(e).splitlines()[0]}")
        return False
    v["qa"] = res
    ss[f"rev_{i}"] = res.get("revision_prompt", "")
    return True


def regenerate_from_qa(i: int) -> bool:
    """검수 수정안 + 해당 이미지로 다시 생성 → 새 버전을 목록 아래에 추가."""
    v = ss.versions[i]
    text = (ss.get(f"rev_{i}") or (v.get("qa") or {}).get("revision_prompt", "")).strip()
    if not text:
        st.warning("수정 프롬프트가 비어 있어요.")
        return False
    note = f"v{i + 1} 검수 반영 수정본"
    if use_codex:
        refs, projs = _write_work_files()
        base = f"base_v{i + 1}.png"
        (CODEX_DIR / base).write_bytes(v["png"])
        prompt = (f"{text}\n\nAttached: `{base}` = the diagram to revise (edit this image); "
                  "`1_sketch.png` = original sketch (structure reference)"
                  + (f"; {', '.join(refs)} = style references" if refs else "")
                  + (f"; {', '.join(projs)} = my design drawings (content facts — do not invent anything beyond them)"
                     if projs else "") + f".\n{prompts.DETAIL_EN[detail]}\n{prompts.EFFICIENCY_EN}")
        mp = ["4_material_map.png"] if map_on() else []
        return _codex_call(prompt, [base, "1_sketch.png", *refs, *projs, *mp], note, ss.get("codex_session"))
    if use_api:
        with st.spinner(f"v{i + 1} 검수 수정안으로 다시 생성 중..."):
            png = render(v["png"], ref_bytes, text)
        register_result(png, note, prompt=text)
        return True
    return False


def import_result(note: str) -> None:
    if b := clipboard_or_warn():
        register_result(b, note)
        st.toast(f"v{len(ss.versions)}로 가져왔어요.")
        st.rerun()


# ================================================================ UI
# ---------------------------------------------------------------- ① 어떤 다이어그램
TYPE_OPTIONS = {"다이어그램": DIAGRAM_TYPES, "평면 리터칭": PLAN_TYPES, "단면 리터칭": SECTION_TYPES,
                "렌더링": RENDER_TYPES}
st.subheader("① 어떤 다이어그램인가요?  (가장 우선)" if not is_drawing else f"① 어떤 {work_type}인가요?  (가장 우선)")
st.pills({"다이어그램": "유형", "렌더링": "렌더 초점 (시간대·카메라·분위기)"}.get(work_type, "리터칭 초점")
         + " (여러 개 선택 가능)", TYPE_OPTIONS[work_type], selection_mode="multi", key=f"types_{work_type}")
st.text_area(
    {"다이어그램": "무엇을 보여주는 다이어그램인지", "렌더링": "이 렌더링으로 무엇을 보여주고 싶은지"}.get(
        work_type, "이 도면으로 무엇을 보여주고 싶은지"),
    key="diagram_goal",
    height=80,
    placeholder={
        "다이어그램": "예: 대지 경사를 따라 매스가 3단계로 쪼개지며 중정이 생기는 과정. 1층은 공용, 2~3층은 주거.",
        "렌더링": "예: 가로에서 본 저층부. 열린 1층 카페와 중정으로 들어가는 입구가 활기 있게 보이도록.",
    }.get(work_type, "예: 1층 평면. 공용(로비·카페)과 주거 출입을 색으로 구분하고, 중정과 이어지는 동선이 잘 보이게."),
)

if is_render:
    with st.expander("🎨 렌더링 설정 — 재료 지정 · 재료 색 코딩 맵", expanded=True):
        r1, r2 = st.columns(2)
        with r1:
            st.text_area("재료 지정 (부위: 재료) — AI는 여기 적힌 재료만 써요", key="materials", height=150,
                         placeholder="예:\n외벽: 노출콘크리트 (송판 무늬)\n창: 투명 로이유리, 실내 따뜻한 조명\n"
                                     "프레임: 짙은 회색 알루미늄\n1층 바닥: 화강석 판석\n루버: 목재")
        with r2:
            st.caption("**재료 색 코딩 맵 (추천)** — 스케치업에서 같은 카메라로 재료마다 단색을 칠해 캡처한 이미지. "
                       "AI가 색 영역 그대로 재료를 입혀서 '어디가 유리·목재인지' 헷갈리지 않아요.")
            mf = st.file_uploader("재료 색 코딩 맵 이미지", type=["png", "jpg", "jpeg", "webp"], key="matmap_file")
            m1, m2 = st.columns(2)
            new_map = None
            if mf and ss.get("matmap_id") != mf.file_id:
                ss.matmap_id, new_map = mf.file_id, mf.getvalue()
            if m1.button("📋 맵 붙여넣기"):
                new_map = clipboard_or_warn()
            if ss.material_map and m2.button("맵 지우기"):
                ss.material_map, ss.material_legend = None, []
                st.rerun()
            if new_map:
                old = dict(ss.material_legend)
                ss.material_map = new_map
                ss.material_legend = [(h, old.get(h, "")) for h, _ in drawing_tools.map_colors(new_map)]
        if ss.material_map:
            import pandas as pd

            mc1, mc2 = st.columns([1, 2])
            mc1.image(ss.material_map, caption="재료 색 코딩 맵", use_container_width=True)
            with mc2:
                st.markdown(" ".join(f"<span style='display:inline-block;width:18px;height:18px;background:{h};"
                                     f"border:1px solid #888;margin-right:4px'></span>{h}"
                                     for h, _ in ss.material_legend), unsafe_allow_html=True)
                leg = st.data_editor(pd.DataFrame([{"색": h, "재료": m} for h, m in ss.material_legend]),
                                     column_config={"색": st.column_config.TextColumn(disabled=True),
                                                    "재료": st.column_config.TextColumn(required=False)},
                                     hide_index=True, use_container_width=True,
                                     key="legend_" + str(abs(hash(tuple(h for h, _ in ss.material_legend)))))
                ss.material_legend = [(r["색"], str(r["재료"] or "")) for _, r in leg.iterrows()]
                st.caption("색마다 재료를 적어주세요. 비워둔 색은 범례에서 빠져요.")

MAX_PROJECT = 6
with st.expander("📐 내 설계 자료 (선택) — 내 의도와 다른 내용이 나오지 않게",
                 expanded=bool(ss.get("project_text") or ss.pasted_projects)):
    st.caption("내가 이미 만든 도면·다이어그램과 프로그램·설계 논리 글을 넣으면, AI가 이걸 **내용의 기준**으로 삼아 "
               "없는 프로그램·라벨·숫자를 지어내지 않아요. 스타일은 여기서 가져오지 않고 ② 레퍼런스에서만 가져와요. "
               "Claude 검토·검수도 이 자료와 어긋나는지 확인해요.")
    pc1, pc2 = st.columns(2)
    with pc1:
        pfiles = st.file_uploader("설계 도면·다이어그램 이미지 (평면·단면·배치도, 기존 다이어그램 등)",
                                  type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="project_files")
        pp1, pp2 = st.columns(2)
        if pp1.button("📋 도면 붙여넣기", help="캐드·라이노·PDF 뷰어 등에서 캡처/복사한 이미지를 추가"):
            if b := clipboard_or_warn():
                ss.pasted_projects.append(b)
        if ss.pasted_projects and pp2.button("붙인 도면 비우기"):
            ss.pasted_projects = []
            st.rerun()
        cad_files = st.file_uploader(
            "CAD·스케치업 파일 (.dxf / .skp)", type=["dxf", "skp"], accept_multiple_files=True, key="cad_files",
            help="DXF: 도면을 이미지로 그리고, 도면 속 글자(실명·면적·층 표기)를 설계 글에 넣어요. "
                 "AutoCAD에서 '다른 이름으로 저장 → DXF'.\n\n"
                 "SKP(시험 기능): 형상은 못 읽고, 파일 속 미리보기 이미지와 이름(컴포넌트·태그·장면 등)만 뽑아요.")
        for cf in cad_files or []:
            if cf.file_id in ss.cad_items:
                continue
            with st.spinner(f"{cf.name} 읽는 중..."):
                try:
                    if cf.name.lower().endswith(".dxf"):
                        png, txt = cad_import.dxf_to_png_and_text(cf.getvalue())
                        label = "도면 글자"
                    else:
                        png, txt = cad_import.skp_extract(cf.getvalue())
                        label = "스케치업 이름 정보"
                except Exception as e:  # noqa: BLE001
                    st.error(f"{cf.name}을(를) 읽지 못했어요: {str(e)[:150]}")
                    ss.cad_items[cf.file_id] = {"png": None}
                    continue
            ss.cad_items[cf.file_id] = {"png": png}
            if txt:
                ss.project_text = (ss.project_text + "\n\n" if ss.project_text.strip() else "") + \
                    f"[{label}: {cf.name}]\n{txt}"
            if not png:
                st.info(f"{cf.name}: 미리보기 이미지가 없어요. 스케치업에서 장면을 PNG로 내보내 넣어주세요.")
        cad_pngs = [ss.cad_items[f.file_id]["png"] for f in cad_files or []
                    if ss.cad_items.get(f.file_id, {}).get("png")]
        project_bytes = ([f.getvalue() for f in pfiles] if pfiles else []) + cad_pngs + ss.pasted_projects
        if len(project_bytes) > MAX_PROJECT:
            st.warning(f"도면은 {MAX_PROJECT}장까지만 보내요 (이미지가 많으면 AI가 헷갈려요). 앞의 {MAX_PROJECT}장을 써요.")
            project_bytes = project_bytes[:MAX_PROJECT]
        if project_bytes:
            st.image(project_bytes, width=90)
    with pc2:
        tfile = st.file_uploader("설계 글 파일 (.txt .md .pdf .docx) — 글자만 뽑아서 아래에 넣어요",
                                 type=["txt", "md", "pdf", "docx"], key="project_doc")
        if tfile and ss.get("project_doc_id") != tfile.file_id:
            ss.project_doc_id = tfile.file_id
            try:
                extracted = bridge.extract_text(tfile.name, tfile.getvalue())
                ss.project_text = (ss.project_text + "\n\n" if ss.project_text.strip() else "") + extracted
                if not extracted:
                    st.warning("파일에서 글자를 찾지 못했어요 (스캔한 PDF는 글자가 없어요). 이미지로 넣어주세요.")
            except Exception as e:  # noqa: BLE001
                st.error(f"파일을 읽지 못했어요: {e}")
        st.text_area("프로그램·설계 논리 (직접 쓰거나 붙여넣기)", key="project_text", height=170,
                     placeholder="예: 1층 로비·카페(공용), 2~3층 공유오피스, 4~10층 주거 120세대. "
                                 "대지 중앙 30×30m 중정이 동선과 프로그램을 묶는다. 경사를 따라 3단으로 내려간다.")
        if len(ss.project_text) > 3000:
            st.caption(f"글이 길어요 ({len(ss.project_text)}자). 앞의 3,000자만 프롬프트에 들어가요 — 핵심만 남기면 더 정확해요.")
    st.checkbox("🔒 설계 자료와 스케치에 없는 내용은 추가하지 않기 (엄격)", value=True, key="facts_strict",
                help="켜면: 자료에 없는 프로그램·라벨·숫자·설계 행위를 지어내지 말라고 지시하고, 검수에서도 잡아내요.")

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
    if ss.anchor:
        a1, a2 = st.columns([1, 3])
        a1.image(ss.anchor["png"], width=90)
        with a2:
            st.checkbox("⭐ 기준 컷을 레퍼런스로 사용 (같은 프로젝트 톤 맞추기)", value=True, key="use_anchor")
            st.caption(f"기준 컷: {ss.anchor['note']}")
            if st.button("기준 컷 해제"):
                ss.anchor = None
                st.rerun()
        if anchor_on():
            ref_bytes = ref_bytes + [ss.anchor["png"]]

    ss.mood = st_keyup(
        "원하는 느낌 (문장으로 자유롭게)",
        value=ss.mood,
        key=f"mood_{ss.mood_ver}",
        debounce=900,
        placeholder="예: 따뜻하고 손으로 그린 듯한 느낌, 동선이 한눈에 보였으면",
    ) or ""

    # 구절별 추천: (구절, 직접 대체 그래픽 키워드, 비슷한 느낌의 건축 언어)
    types = current_types()
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
        _pills("자주 쓰는 키워드", DEFAULTS_BY_WORK[work_type], f"default_{work_type}")
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

has_input = bool(goal_text() or ref_bytes or ss.mood or ss.picked or project_bytes or ss.project_text.strip())

# ---------------------------------------------------------------- ③ 스케치 + 생성
with c2:
    st.subheader(f"③ {INPUT_LABEL[work_type]}")
    if is_render:
        st.caption("스케치업·라이노에서 **그림자 끄고, 배경 단색, 화이트/클레이 모델**로 캡처하면 형태가 덜 바뀌어요. "
                   "카메라는 장면(Named View)으로 저장해 두세요.")
    t_clip, t_dir, t_file, t_dxf = st.tabs(["📋 클립보드", "📁 폴더", "📄 파일", "📐 DXF 도면"])
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
    with t_dxf:
        st.caption("AutoCAD에서 **DXF로 저장**한 도면을 레이어별로 정리해 바탕 도면으로 써요. "
                   "벽은 굵게·검정 채움(포셰), 창호는 가늘게, 가구는 회색, 치수·도곽은 숨기기 — AI 없이 정확하게 정리돼요.")
        dx = st.file_uploader("DXF 도면", type=["dxf"], key="sketch_dxf")
        if dx:
            if ss.get("dxf_id") != dx.file_id:
                ss.dxf_id = dx.file_id
                try:
                    ss.dxf_layers = cad_import.dxf_layers(dx.getvalue())
                except Exception as e:  # noqa: BLE001
                    st.error(f"DXF를 읽지 못했어요: {str(e)[:150]}")
                    ss.dxf_layers = []
            if ss.get("dxf_layers"):
                import pandas as pd

                st.caption("레이어 이름으로 역할을 추천했어요. 필요하면 '역할' 칸을 눌러 바꾸세요.")
                edited = st.data_editor(
                    pd.DataFrame([{"레이어": n, "객체 수": c, "역할": r} for n, c, r in ss.dxf_layers]),
                    column_config={
                        "레이어": st.column_config.TextColumn(disabled=True),
                        "객체 수": st.column_config.NumberColumn(disabled=True),
                        "역할": st.column_config.SelectboxColumn(options=cad_import.ROLES, required=True),
                    },
                    hide_index=True, use_container_width=True, key=f"dxf_editor_{dx.file_id}",
                )
                fill = st.checkbox("벽 레이어의 닫힌 선을 검정으로 채우기 (포셰)", value=True)
                if st.button("📐 정리된 도면을 사용", type="primary"):
                    with st.spinner("도면 정리 중..."):
                        try:
                            png = cad_import.dxf_render_styled(dx.getvalue(), dict(zip(edited["레이어"], edited["역할"])),
                                                               fill)
                            ss.sketch_bytes, ss.sketch_src = png, f"{dx.name} (레이어 정리)"
                        except Exception as e:  # noqa: BLE001
                            st.error(f"도면을 그리지 못했어요: {str(e)[:150]}")

    if ss.sketch_bytes:
        st.image(ss.sketch_bytes, caption=f"{INPUT_LABEL[work_type]} · {ss.sketch_src}",
                 use_container_width=True)

    extra = st.text_input("추가 지시 (선택)", placeholder="예: 동선은 주황 화살표, 라벨은 영어로")
    ready = bool(ss.sketch_bytes and has_input)
    if not ready:
        st.caption(f"{'스케치' if not is_drawing else '도면'} + (① 설명이나 ② 분위기/레퍼런스 중 하나 이상)이 필요해요.")

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
        if multipass:
            base = ss.sketch_bytes
            for k, (instr, pname) in enumerate(zip(prompts.PASSES_EN, prompts.PASS_NAMES)):
                with st.spinner(f"🪜 {pname} 생성 중..."):
                    png = render(base, ref_bytes, f"{instr} {extra}")
                register_result(png, f"초기 생성 · {pname}", qa=k == 2 or pass_qa)
                base = ss.versions[-1]["png"]
        else:
            with st.spinner("생성 중... (30초~1분)"):
                png = render(ss.sketch_bytes, ref_bytes, "Redraw IMAGE 1 as a finished image. " + extra)
            register_result(png, "초기 생성")
        ss.chat.append(("assistant", f"v{len(ss.versions)} 생성 완료. 수정할 점을 채팅으로 알려주세요."))

# ---------------------------------------------------------------- ④ 결과 (버전 목록: 새 버전은 아래에 추가)
if ss.versions:
    st.divider()
    st.subheader("④ 결과 & 수정")
    h1, h2, h3 = st.columns([1, 1, 3])
    # PPT는 버튼을 눌렀을 때만 만든다 (매 화면 갱신마다 만들면 결과가 쌓일수록 느려짐)
    if ss.get("pptx_n") == len(ss.versions) and ss.get("pptx"):
        h1.download_button("⬇️ PPT 받기", ss.pptx, "diagrams.pptx",
                           "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    elif h1.button("PPT 만들기 (전체 버전)"):
        with st.spinner("PPT 만드는 중..."):
            ss.pptx = bridge.build_pptx([(x["png"], f"v{i + 1} · {x['note']}") for i, x in enumerate(ss.versions)])
            ss.pptx_n = len(ss.versions)
        st.rerun()
    if h2.button("결과 폴더"):
        bridge.open_folder(OUT_DIR)
    h3.caption("새로 만든 이미지는 기존 이미지를 대체하지 않고 아래에 추가돼요.")
    can_regen = use_codex or use_api

    for i, v in enumerate(ss.versions):
        with st.container(border=True):
            left, right = st.columns([3, 2])
            with left:
                st.image(v["png"], caption=f"v{i + 1} · {v['note']}", use_container_width=True)
                b4, b5 = st.columns(2)
                if b4.button("🔍 형태 비교", key=f"diff_{i}", disabled=not ss.sketch_bytes,
                             help="입력과 결과의 윤곽선을 겹쳐 비교: 빨강 = 사라진 윤곽, 파랑 = 새로 생긴 윤곽"):
                    compute_diff(v)
                    st.rerun()
                if b5.button("⭐ 기준 컷으로 지정", key=f"anchor_{i}",
                             help="이 이미지를 같은 프로젝트의 기준 컷으로 저장해서, 다음 컷 생성 때 레퍼런스로 자동 첨부"):
                    ss.anchor = {"png": v["png"], "note": f"v{i + 1} · {v['note']}"}
                    st.toast("기준 컷으로 지정했어요. 다음 생성부터 레퍼런스로 함께 보내요.")
                    st.rerun()
                if (v.get("diff") or {}).get("png"):
                    with st.expander(f"🔍 형태 비교 · 사라진 윤곽 {v['diff']['pct']}% ({v['diff']['how']})"):
                        st.image(v["diff"]["png"], caption="빨강 = 모델에 있었는데 사라진 윤곽 · 파랑 = 새로 생긴 윤곽 "
                                                            "(질감·사람·나무로 생긴 작은 파랑은 정상)",
                                 use_container_width=True)
                elif v.get("diff"):
                    st.caption(v["diff"]["how"])
                b1, b2, b3 = st.columns(3)
                if b3.button("📐 원본 선 덮기", key=f"lock_{i}", disabled=not ss.sketch_bytes,
                             help="이 이미지 위에 원본 도면/스케치의 선을 겹친 새 버전을 아래에 추가해요"):
                    locked, how = drawing_tools.lock_lines(v["png"], ss.sketch_bytes, lock_opacity, lock_threshold)
                    add_version(locked, f"v{i + 1} + 원본 선 고정 ({how})", v.get("prompt", ""))
                    st.rerun()
                if b1.button("📋 이미지 복사", key=f"copy_{i}", help="포토샵·PPT·ChatGPT에 Ctrl+V"):
                    try:
                        bridge.copy_to_clipboard(v["png"])
                        st.toast(f"v{i + 1} 이미지를 복사했어요.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"복사 실패: {e}")
                b2.download_button("PNG 저장", v["png"], f"diagram_v{i + 1}.png", "image/png", key=f"png_{i}")
            with right:
                st.markdown(f"#### v{i + 1}")
                qa = v.get("qa")
                if qa is None:
                    st.caption("아직 Claude 검수 전이에요.")
                    if st.button("🔎 Claude로 검수", key=f"qa_{i}", disabled=not (qa_engine()[0] and ss.sketch_bytes)):
                        if run_qa(i):
                            st.rerun()
                elif qa["verdict"] == "revise":
                    st.warning("⚠️ Claude 검수: 수정이 필요해요")
                    st.markdown(qa["issues_ko"])
                    st.text_area("수정 프롬프트 (직접 고칠 수 있어요)", key=f"rev_{i}", height=180)
                    if can_regen and st.button("🔁 이 수정안으로 다시 생성 (원클릭)", key=f"regen_{i}", type="primary",
                                                use_container_width=True):
                        if regenerate_from_qa(i):
                            st.rerun()
                    c1, c2 = st.columns(2)
                    if c1.button("📝 수정 프롬프트 복사", key=f"copyrev_{i}"):
                        try:
                            bridge.copy_text(ss.get(f"rev_{i}", ""))
                            st.toast("수정 프롬프트를 복사했어요.")
                        except Exception as e:  # noqa: BLE001
                            st.error(f"복사 실패: {e}")
                    if c2.button("🖼️ 이 이미지 복사", key=f"copyimg_{i}"):
                        try:
                            bridge.copy_to_clipboard(v["png"])
                            st.toast("이미지를 복사했어요.")
                        except Exception as e:  # noqa: BLE001
                            st.error(f"복사 실패: {e}")
                    if not can_regen:
                        st.caption("ChatGPT 구독 모드: 이미지와 수정 프롬프트를 복사해 ChatGPT에 붙여넣고, "
                                   "결과를 아래 '새 버전 가져오기'로 추가하세요.")
                else:
                    st.success("✅ Claude 검수 통과 — 이대로 써도 좋아요")
                    if qa.get("issues_ko") and qa["issues_ko"].strip() != "문제 없음":
                        with st.expander("검수 메모"):
                            st.markdown(qa["issues_ko"])
                    if st.button("🔎 다시 검수", key=f"reqa_{i}"):
                        if run_qa(i):
                            st.rerun()

    # 자유 수정 요청 (가장 최근 버전 기준)
    last = len(ss.versions) - 1
    if use_chatgpt:
        st.markdown("**수정은 ChatGPT에서** 이어서 요청하고, 새 결과가 나올 때마다 가져오세요.")
        note = st.text_input("메모 (선택)", placeholder="예: 매스 반투명 처리")
        if st.button("📥 새 버전 가져오기 (클립보드)"):
            import_result(note or "ChatGPT 수정본")
    else:
        with st.expander("대화 기록", expanded=False):
            for role, text in ss.chat:
                st.chat_message(role).write(text)
        req = st.chat_input(f"v{last + 1}에 대한 수정 요청 (예: 2층 매스를 더 투명하게, 라벨 폰트 작게)")
        if req:
            ss.chat.append(("user", req))
            v = ss.versions[last]
            if use_codex:
                if codex_revise(v["png"], last, req, ref_bytes):
                    st.rerun()
            else:
                with st.spinner(f"v{last + 1} 기준으로 수정 중..."):
                    png = render(v["png"], ref_bytes,
                                 f"Keep everything from IMAGE 1 unchanged except this revision: {req}")
                ss.chat.append(("assistant", f"v{len(ss.versions) + 1} 완료 (v{last + 1} 기반)."))
                register_result(png, req)
                st.rerun()
