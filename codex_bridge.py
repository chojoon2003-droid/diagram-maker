"""
Codex CLI 연동: ChatGPT 구독(Codex 로그인)으로 GPT-6 Astra + 이미지 생성을 앱에서 자동 실행.

사전 준비 (한 번만):
  1) Node.js 설치  2) npm install -g @openai/codex  3) codex login  (ChatGPT 계정으로 로그인)

동작: 작업 폴더에 스케치·레퍼런스를 두고
  codex exec --skip-git-repo-check --sandbox workspace-write -m <모델> -i 이미지... -   (프롬프트는 stdin)
을 실행 → 생성된 PNG를 찾아 돌려준다. 수정 요청은 같은 세션을 이어서(resume) 실행.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
EFFORT = {"빠르게": "low", "자동": "medium", "깊게 생각": "high"}
SETUP_HELP = (
    "Codex가 설치되어 있지 않아요. 한 번만 준비하면 돼요:\n"
    "1. Node.js 설치 (https://nodejs.org → LTS)\n"
    "2. 명령 프롬프트에서: npm install -g @openai/codex\n"
    "3. 이어서: codex login  → 브라우저에서 ChatGPT 계정으로 로그인\n"
    "4. 이 앱을 다시 실행"
)


def find_codex() -> str | None:
    return shutil.which("codex")


def codex_version() -> str:
    exe = find_codex()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001
        return ""


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _session_id(log: str) -> str | None:
    for line in log.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for k in ("thread_id", "session_id", "conversation_id"):
                if isinstance(obj.get(k), str):
                    return obj[k]
    m = re.search(r"session[ _]id[\"']?\s*[:=]\s*[\"']?([0-9a-fA-F-]{36})", log)
    return m.group(1) if m else None


def _find_image(workdir: Path, out_name: str, inputs: set[str], since: float, log: str) -> Path | None:
    target = workdir / out_name
    if target.exists() and target.stat().st_mtime >= since - 1:
        return target
    for m in re.finditer(r"SAVED:\s*(.+\.png)", log, flags=re.I):
        p = Path(m.group(1).strip().strip("`'\""))
        p = p if p.is_absolute() else workdir / p
        if p.exists():
            return p
    fresh = [p for p in workdir.glob("*.png") if p.name not in inputs and p.stat().st_mtime >= since - 1]
    gen_dir = _codex_home() / "generated_images"
    if gen_dir.exists():
        fresh += [p for p in gen_dir.rglob("*.png") if p.stat().st_mtime >= since - 1]
    return max(fresh, key=lambda p: p.stat().st_mtime) if fresh else None


def _exec(args: list[str], prompt: str, workdir: Path, timeout: int) -> tuple[int, str]:
    r = subprocess.run(args, input=prompt.encode("utf-8"), cwd=workdir, capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")


def run(workdir: Path, prompt: str, images: list[str], out_name: str, model: str, effort: str,
        session_id: str | None = None, timeout: int = 900) -> dict:
    """Codex로 이미지 생성. 반환: {"png": bytes, "session_id": str|None, "log": str}"""
    exe = find_codex()
    if not exe:
        raise RuntimeError(SETUP_HELP)
    full_prompt = (
        f"{prompt}\n\n"
        "HOW TO DELIVER (Codex):\n"
        "- Use the built-in image generation tool ($imagegen) with the attached image(s) as input/reference.\n"
        "- Do not write code, install anything or call external APIs.\n"
        "- Generate once. Do not open, inspect, critique or re-check the generated image, and do not regenerate it "
        "unless the tool failed — a separate reviewer checks it.\n"
        f"- Save the final image as `{out_name}` in the current directory, then print a line `SAVED: {out_name}`."
    )
    common = ["--skip-git-repo-check", "--sandbox", "workspace-write", "-m", model,
              "-c", f"model_reasoning_effort={effort}"]
    for im in images:
        common += ["-i", im]
    start = time.time()
    attempts = []
    if session_id:  # 이전 대화 이어서 (수정 요청)
        attempts.append([exe, "exec", "resume", session_id, *common, "--json", "-"])
    attempts += [[exe, "exec", *common, "--json", "-"], [exe, "exec", *common, "-"]]

    log, code = "", 1
    for args in attempts:
        try:
            code, out = _exec(args, full_prompt, workdir, timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Codex가 {timeout // 60}분 안에 끝나지 않았어요. 다시 시도하거나 화질/생각 수준을 낮춰보세요.") from None
        log += out
        if code == 0:
            break
        if "unexpected argument" not in out and "resume" not in args:
            break  # 옵션 문제가 아니면 다른 방식으로 재시도해도 의미 없음
    if code != 0:
        hint = ""
        low = log.lower()
        if "login" in low or "unauthorized" in low or "401" in low:
            hint = "\n→ 명령 프롬프트에서 `codex login`으로 ChatGPT 계정 로그인을 해주세요."
        elif "model" in low and ("not found" in low or "not supported" in low or "does not exist" in low):
            hint = f"\n→ 모델 `{model}`을(를) 쓸 수 없어요. 사이드바 'Codex 모델'을 바꿔보세요."
        elif "rate" in low or "usage limit" in low:
            hint = "\n→ Codex 사용 한도에 걸렸어요. 잠시 후 다시 시도하세요."
        raise RuntimeError("Codex 실행 실패" + hint + "\n\n" + log[-1500:])

    img = _find_image(workdir, out_name, {Path(i).name for i in images}, start, log)
    if not img:
        raise RuntimeError("Codex가 실행은 끝났지만 생성된 이미지를 찾지 못했어요.\n\n" + log[-1500:])
    return {"png": img.read_bytes(), "session_id": _session_id(log) or session_id, "log": log}


# ------------------------------------------------------------------ 로그인 (크롬으로 열기)
_login_proc = None  # 로그인 완료까지 프로세스를 살려두기 위한 참조


def login_status() -> str:
    """'로그인됨 ...' / '로그인 안 됨' / '' (Codex 없음)."""
    exe = find_codex()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "login", "status"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    except Exception:  # noqa: BLE001
        return "확인 불가"
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    return ("로그인됨 · " + out.splitlines()[0]) if r.returncode == 0 and out else "로그인 안 됨"


def start_login(open_url, wait: float = 60.0) -> str:
    """`codex login`을 실행하고, 출력되는 로그인 주소를 open_url(주소)로 연다 (예: 크롬).
    로그인은 백그라운드에서 계속 진행되고, 브라우저에서 완료하면 자동으로 끝난다. 연 주소를 돌려준다."""
    global _login_proc
    import threading

    exe = find_codex()
    if not exe:
        raise RuntimeError(SETUP_HELP)
    _login_proc = subprocess.Popen([exe, "login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    found: list[str] = []
    done = threading.Event()

    def reader():
        for raw in iter(_login_proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace")
            m = re.search(r"https://\S+", line)
            if m and not found and ("auth" in m.group(0) or "login" in m.group(0) or "oauth" in m.group(0)):
                found.append(m.group(0).rstrip(".,)'\""))
                done.set()
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(wait)
    if not found:
        raise RuntimeError("Codex 로그인 주소를 받지 못했어요. 명령 프롬프트에서 `codex login`을 직접 실행해 주세요.")
    open_url(found[0])
    return found[0]


def selftest(model: str, timeout: int = 240) -> tuple[bool, float, str]:
    """이미지 없이 아주 짧은 요청으로 Codex가 실제로 응답하는지 확인. (성공 여부, 걸린 초, 출력 요약)"""
    import tempfile

    exe = find_codex()
    if not exe:
        return False, 0.0, "Codex가 설치되어 있지 않아요."
    t = time.time()
    with tempfile.TemporaryDirectory() as d:
        try:
            code, out = _exec([exe, "exec", "--skip-git-repo-check", "-m", model,
                               "-c", "model_reasoning_effort=low", "-"],
                              "Reply with exactly: OK. Do not run any tools.", Path(d), timeout)
        except subprocess.TimeoutExpired:
            return False, time.time() - t, f"{timeout}초 안에 응답이 없어요."
    return code == 0 and "OK" in out, time.time() - t, out[-400:]
