"""
Claude Code 연결 테스터 (기존 앱과 별개)

앱 → 내 컴퓨터의 Claude Code(내 Claude 구독 계정)로 요청이 잘 가고, 답이 잘 돌아오는지만 확인한다.
 1) 설치·로그인 상태
 2) 글 질문 테스트
 3) 이미지 읽기 테스트 (검수 기능이 쓰는 방식과 같음: 폴더의 이미지 파일을 Claude Code가 직접 읽음)
실행: test_claude_code.bat 더블클릭
"""

import io
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

import claude_cli

NO_WINDOW = claude_cli.NO_WINDOW
st.set_page_config(page_title="Claude Code 연결 테스터", layout="centered")
st.title("🧪 Claude Code 연결 테스터")
st.caption("이 화면은 기존 앱과 별개예요. 여기서 보내는 내용은 **내 컴퓨터의 Claude Code**(내 Claude 구독 계정)로 가고, "
           "claude.ai 웹·데스크탑 앱의 대화 목록에는 나타나지 않아요. 구독 사용량은 조금 차감돼요.")


def run_claude(prompt: str, model: str, workdir: Path | None = None, allow_read: bool = False,
               timeout: int = 600) -> dict:
    exe = claude_cli.find_claude()
    if not exe:
        return {"ok": False, "error": "Claude Code를 찾지 못했어요 (설치 확인)."}
    args = [exe, "-p", "--output-format", "json", "--model", model]
    if allow_read:
        args += ["--allowedTools", "Read"]
    t = time.time()
    try:
        r = subprocess.run(args, input=prompt.encode("utf-8"), cwd=workdir, capture_output=True,
                           timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{timeout}초 안에 응답이 없어요.", "sec": time.time() - t}
    out = r.stdout.decode("utf-8", "replace").strip()
    err = r.stderr.decode("utf-8", "replace").strip()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except json.JSONDecodeError:
        data = {}
    ok = r.returncode == 0 and bool(data) and not data.get("is_error")
    return {"ok": ok, "sec": time.time() - t, "data": data, "raw": out, "stderr": err, "code": r.returncode,
            "cmd": " ".join(a if " " not in a else f'"{a}"' for a in args)}


def show(res: dict) -> None:
    if res.get("error"):
        st.error(res["error"])
        return
    (st.success if res["ok"] else st.error)(
        f"{'✅ 응답 받음' if res['ok'] else '❌ 실패'} · {res['sec']:.1f}초")
    d = res.get("data") or {}
    if d.get("result"):
        st.markdown("**Claude Code의 답:**")
        st.info(d["result"])
    meta = {k: d.get(k) for k in ("session_id", "num_turns", "duration_ms", "total_cost_usd") if k in d}
    if meta:
        st.caption(" · ".join(f"{k}: {v}" for k, v in meta.items()))
    with st.expander("원본 응답 / 오류 출력 (문제가 있으면 이걸 캡처해 주세요)"):
        st.caption(f"실행한 명령: `{res.get('cmd', '')}` · 종료 코드 {res.get('code')}")
        st.code(res.get("raw") or "(stdout 없음)", language="json")
        if res.get("stderr"):
            st.code(res["stderr"][-2000:], language=None)


# ---------------------------------------------------------------- 1. 상태
st.subheader("1. 설치·로그인 상태")
exe = claude_cli.find_claude()
c1, c2 = st.columns(2)
c1.metric("설치", "✅ 있음" if exe else "❌ 없음")
c2.metric("로그인", claude_cli.login_status() if exe else "-")
if exe:
    st.caption(f"위치: `{exe}` · 버전: {claude_cli.claude_version() or '확인 불가'}"
               + ("" if shutil.which("claude") else " · (PATH에는 없지만 설치 위치에서 찾았어요)"))
if st.button("🔄 다시 확인"):
    st.rerun()

model = st.radio("테스트 모델", ["sonnet", "opus", "haiku"], horizontal=True,
                 help="sonnet: 빠르고 사용량 적음 (테스트 추천) · opus: 에이전트 검토·검수 기본값")

# ---------------------------------------------------------------- 2. 글 질문
st.subheader("2. 글 질문 테스트")
q = st.text_area("보낼 내용", "건축 다이어그램에서 '포셰(poché)'가 뭔지 한 문장으로 설명해줘.", height=80)
if st.button("📨 Claude Code로 보내기", type="primary", disabled=not (exe and q.strip())):
    with st.spinner("Claude Code 응답 기다리는 중... (보통 5~30초)"):
        st.session_state.text_res = run_claude(q, model)
if st.session_state.get("text_res"):
    show(st.session_state.text_res)

# ---------------------------------------------------------------- 3. 이미지 읽기
st.subheader("3. 이미지 읽기 테스트")
st.caption("에이전트의 검토·검수는 Claude Code가 폴더의 이미지 파일을 직접 읽는 방식이에요. 그게 되는지 확인해요. "
           "이미지를 안 올리면 글자 'TEST 4721'이 적힌 샘플 그림으로 테스트해요 — 답에 4721이 나오면 성공.")
up = st.file_uploader("테스트할 이미지 (선택)", type=["png", "jpg", "jpeg", "webp"])


def sample_png() -> bytes:
    im = Image.new("RGB", (800, 500), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 380, 420], outline="black", width=8)
    d.ellipse([460, 120, 740, 400], outline="blue", width=8)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default(size=64)
    except TypeError:
        font = None
    d.text((100, 200), "TEST 4721", fill="red", font=font)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


img = up.getvalue() if up else sample_png()
st.image(img, width=320, caption="보낼 이미지" + ("" if up else " (샘플)"))
iq = st.text_input("질문", "test_image.png 파일을 읽고, 그림에 있는 도형과 글자를 한국어로 짧게 설명해줘.")
if st.button("🖼️ 이미지 읽기 테스트", type="primary", disabled=not exe):
    with tempfile.TemporaryDirectory() as d:
        Image.open(io.BytesIO(img)).convert("RGB").save(Path(d) / "test_image.png", format="PNG")
        with st.spinner("Claude Code가 이미지를 읽는 중... (보통 10~60초)"):
            st.session_state.img_res = run_claude(
                f"Use the Read tool to open test_image.png in the current directory. {iq}", model,
                workdir=Path(d), allow_read=True)
if st.session_state.get("img_res"):
    res = st.session_state.img_res
    show(res)
    if res.get("ok") and not up:
        ans = (res.get("data") or {}).get("result", "")
        if "4721" in ans:
            st.success("🎉 샘플 글자 4721을 정확히 읽었어요 — 에이전트 검수에 필요한 이미지 읽기가 정상이에요.")
        else:
            st.warning("답에 4721이 없어요. 이미지를 제대로 못 읽었을 수 있어요 — 원본 응답을 캡처해서 보내주세요.")
