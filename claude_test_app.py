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


def show_usage(d: dict) -> None:
    """Claude Code가 돌려준 사용량(토큰) 표시"""
    u = d.get("usage") or {}
    if not u and not d.get("modelUsage"):
        st.caption("이 응답에는 토큰 정보가 없어요.")
        return
    st.markdown("**사용량 (토큰)**")
    cols = st.columns(4)
    cols[0].metric("입력", f"{u.get('input_tokens', 0):,}")
    cols[1].metric("출력", f"{u.get('output_tokens', 0):,}")
    cols[2].metric("캐시 읽기", f"{u.get('cache_read_input_tokens', 0):,}")
    cols[3].metric("캐시 쓰기", f"{u.get('cache_creation_input_tokens', 0):,}")
    for model_name, mu in (d.get("modelUsage") or {}).items():
        st.caption(f"모델 `{model_name}` · 입력 {mu.get('inputTokens', 0):,} · 출력 {mu.get('outputTokens', 0):,} · "
                   f"캐시 읽기 {mu.get('cacheReadInputTokens', 0):,}")
    if d.get("total_cost_usd") is not None:
        st.caption(f"참고 금액: ${d['total_cost_usd']:.4f} — API로 썼다면 드는 비용의 환산값이에요. "
                   "구독(Pro/Max) 로그인으로 쓰면 이 금액이 청구되지 않고, 구독 사용 한도에서 차감돼요.")
    if d.get("duration_ms"):
        st.caption(f"Claude 처리 시간: {d['duration_ms'] / 1000:.1f}초 (API 대기 {d.get('duration_api_ms', 0) / 1000:.1f}초)")


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
    show_usage(d)
    denials = d.get("permission_denials") or []
    if denials:
        st.warning("🔒 권한이 없어 거부된 작업: " + ", ".join(
            f"{x.get('tool_name', '?')}" + (f" ({(x.get('tool_input') or {}).get('file_path', '')})"
                                            if (x.get("tool_input") or {}).get("file_path") else "")
            for x in denials))
    if d.get("session_id"):
        st.caption(f"세션 ID: `{d['session_id']}` · 주고받은 횟수(turns): {d.get('num_turns', '-')}")
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


# ---------------------------------------------------------------- 4. 권한 테스트
st.subheader("4. 권한 테스트 — 파일·프로그램·이미지를 만들어 달라고 하면?")
st.caption("테스터와 에이전트는 Claude Code에 **파일 읽기(Read)만** 허용해요. 아래 요청을 보내면 Claude Code가 파일을 "
           "만들려고 시도하는지, 실제로 파일이 생기는지, 어떤 권한이 거부됐는지 보여줘요. (빈 임시 폴더에서 실행돼서 "
           "내 파일에는 영향이 없어요)")
PERM_TESTS = {
    "📄 파일 만들기": ("hello.txt 라는 파일을 만들고 '안녕하세요'라고 저장해줘.", "hello.txt"),
    "🐍 프로그램 만들기": ("두 숫자를 더하는 파이썬 프로그램을 calc.py 파일로 만들어줘.", "calc.py"),
    "🖼️ 이미지 만들기": ("파란 원이 그려진 이미지를 만들어서 circle.png 로 저장해줘.", "circle.png"),
}
pick = st.radio("요청", list(PERM_TESTS), horizontal=True)
allow_write = st.checkbox("이번 테스트만 파일 쓰기(Write) 허용해 보기", value=False,
                          help="켜면 Claude Code에 Write 권한을 줘서 실제로 파일이 생기는지 비교해 볼 수 있어요. "
                               "임시 폴더 안에서만 실행돼요.")
if st.button("🔐 권한 테스트 실행", disabled=not exe):
    prompt, fname = PERM_TESTS[pick]
    with tempfile.TemporaryDirectory() as d:
        exe2 = claude_cli.find_claude()
        args = [exe2, "-p", "--output-format", "json", "--model", model]
        if allow_write:
            args += ["--allowedTools", "Write"]
        t = time.time()
        try:
            r = subprocess.run(args, input=prompt.encode("utf-8"), cwd=d, capture_output=True, timeout=600,
                               creationflags=NO_WINDOW)
            out = r.stdout.decode("utf-8", "replace").strip()
            try:
                data = json.loads(out.splitlines()[-1]) if out else {}
            except json.JSONDecodeError:
                data = {}
            made = sorted(p.name for p in Path(d).iterdir())
            st.session_state.perm_res = {
                "ok": r.returncode == 0 and bool(data), "sec": time.time() - t, "data": data, "raw": out,
                "stderr": r.stderr.decode("utf-8", "replace"), "code": r.returncode, "cmd": " ".join(args[1:]),
                "made": made, "target": fname, "write": allow_write,
                "content": (Path(d) / fname).read_text(encoding="utf-8", errors="replace")[:800]
                if (Path(d) / fname).is_file() and not fname.endswith(".png") else "",
            }
        except subprocess.TimeoutExpired:
            st.session_state.perm_res = {"error": "응답 시간 초과"}
if st.session_state.get("perm_res"):
    res = st.session_state.perm_res
    show(res)
    if "made" in res:
        if res["target"] in res["made"]:
            st.success(f"📁 실제로 `{res['target']}` 파일이 만들어졌어요 (Write 허용: {'예' if res['write'] else '아니오'}).")
            if res.get("content"):
                st.code(res["content"], language=None)
        else:
            st.info(f"📁 파일이 만들어지지 않았어요 (폴더 안: {', '.join(res['made']) or '비어 있음'}). "
                    "권한이 없으면 Claude Code는 내용을 답변 글로만 보여줘요.")


# ---------------------------------------------------------------- 5. 사용량 검수 (내 컴퓨터의 Claude Code 기록 합계)
st.subheader("5. 사용량 검수 — 실제로 토큰이 쓰였나?")
st.caption("내 컴퓨터에 저장된 Claude Code 기록(사용자 폴더\\.claude\\projects)을 읽어서, 요청마다 기록된 토큰을 합쳐 보여줘요. "
           "기록은 내 컴퓨터에서만 읽고 어디로도 보내지 않아요.")


def read_usage(days: int) -> list[dict]:
    base = Path.home() / ".claude" / "projects"
    rows, since = [], time.time() - days * 86400
    if not base.exists():
        return rows
    for f in base.rglob("*.jsonl"):
        try:
            if f.stat().st_mtime < since:
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = o.get("message") if isinstance(o, dict) else None
                u = msg.get("usage") if isinstance(msg, dict) else None
                if o.get("type") != "assistant" or not isinstance(u, dict):
                    continue
                rows.append({
                    "time": (o.get("timestamp") or "")[:16].replace("T", " "),
                    "session": (o.get("sessionId") or f.stem)[:8],
                    "folder": Path(o.get("cwd") or "").name or f.parent.name,
                    "model": msg.get("model", ""),
                    "in": int(u.get("input_tokens") or 0), "out": int(u.get("output_tokens") or 0),
                    "cache_r": int(u.get("cache_read_input_tokens") or 0),
                    "cache_w": int(u.get("cache_creation_input_tokens") or 0),
                })
        except OSError:
            continue
    return sorted(rows, key=lambda r: r["time"], reverse=True)


days = st.select_slider("기간", options=[1, 3, 7, 30], value=1, format_func=lambda d: f"최근 {d}일")
if st.button("📊 사용량 검수"):
    st.session_state.usage_rows = read_usage(days)
    st.session_state.usage_days = days
rows = st.session_state.get("usage_rows")
if rows is not None:
    if not rows:
        st.info(f"최근 {st.session_state.usage_days}일 동안 기록된 사용량이 없어요. "
                "(테스터로 질문을 보낸 적이 있는데도 0이면, 다른 사용자 계정으로 실행됐거나 기록 위치가 다를 수 있어요)")
    else:
        tot = {k: sum(r[k] for r in rows) for k in ("in", "out", "cache_r", "cache_w")}
        n_sess = len({r["session"] for r in rows})
        st.success(f"✅ 토큰이 사용됐어요 — 최근 {st.session_state.usage_days}일, 세션 {n_sess}개, 응답 {len(rows)}번")
        c = st.columns(4)
        c[0].metric("입력 합계", f"{tot['in']:,}")
        c[1].metric("출력 합계", f"{tot['out']:,}")
        c[2].metric("캐시 읽기 합계", f"{tot['cache_r']:,}")
        c[3].metric("캐시 쓰기 합계", f"{tot['cache_w']:,}")
        import pandas as pd

        df = pd.DataFrame(rows)
        by_sess = (df.groupby(["session", "folder"], as_index=False)
                   .agg(시작=("time", "min"), 응답수=("in", "size"), 입력=("in", "sum"), 출력=("out", "sum"),
                        캐시읽기=("cache_r", "sum"), 캐시쓰기=("cache_w", "sum"))
                   .sort_values("시작", ascending=False))
        st.markdown("**세션별** (폴더가 diagram-maker 또는 임시 폴더면 테스터·에이전트가 보낸 요청이에요)")
        st.dataframe(by_sess, hide_index=True, use_container_width=True)
        with st.expander("응답별 자세히"):
            st.dataframe(df.rename(columns={"time": "시각", "session": "세션", "folder": "폴더", "model": "모델",
                                            "in": "입력", "out": "출력", "cache_r": "캐시 읽기", "cache_w": "캐시 쓰기"}),
                         hide_index=True, use_container_width=True)
        st.caption("구독 로그인이라면 이 토큰은 돈으로 청구되지 않고 구독 사용 한도에서 차감돼요. "
                   "남은 한도는 Claude Code에서 /usage, 또는 claude.ai → 설정 → 사용량에서 볼 수 있어요.")
