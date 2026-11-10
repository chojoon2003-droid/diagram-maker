"""
Claude Code CLI 연동: Claude 구독(Pro/Max)으로 로그인한 Claude Code가 이미지 파일을 직접 보고
프롬프트를 검토 (추가 API 비용 없음, 구독 사용량에서 차감).

사전 준비 (한 번만): Claude Code 설치 → 명령 프롬프트에서 `claude` 실행 → 구독 계정으로 로그인
동작: 작업 폴더에서  claude -p --output-format json --model <모델> --allowedTools Read  (요청은 stdin)
"""

import json
import platform
import shutil
import subprocess
from pathlib import Path

import prompts

NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
MODELS = {"Opus (가장 꼼꼼)": "opus", "Sonnet (빠름)": "sonnet"}
SETUP_HELP = (
    "Claude Code가 설치되어 있지 않아요. 한 번만 준비하면 돼요:\n"
    "1. https://claude.com/claude-code 의 안내대로 Claude Code 설치\n"
    "2. 폴더의 claude_login_chrome.bat 더블클릭 → 크롬에서 Claude 구독 계정으로 로그인\n"
    "3. 이 앱을 다시 실행"
)


def find_claude() -> str | None:
    return shutil.which("claude")


def claude_version() -> str:
    exe = find_claude()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        return r.stdout.decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001
        return ""


def review(workdir: Path, draft: str, context_ko: str, sketch: str, refs: list[str],
           model: str = "opus", timeout: int = 900) -> dict:
    """반환: {"improved_prompt", "summary_ko", "log"} — 실패 시 RuntimeError(한국어)."""
    exe = find_claude()
    if not exe:
        raise RuntimeError(SETUP_HELP)
    request = prompts.claude_cli_request(draft, context_ko, sketch, refs)
    args = [exe, "-p", "--output-format", "json", "--model", model, "--allowedTools", "Read"]
    try:
        r = subprocess.run(args, input=request.encode("utf-8"), cwd=workdir, capture_output=True,
                           timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude 검토가 {timeout // 60}분 안에 끝나지 않았어요.") from None
    out = r.stdout.decode("utf-8", "replace")
    log = out + "\n" + r.stderr.decode("utf-8", "replace")
    try:
        data = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except json.JSONDecodeError:
        data = {}
    text = data.get("result", "") if isinstance(data, dict) else ""
    if r.returncode != 0 or data.get("is_error") or not text:
        low = log.lower()
        hint = ""
        if "login" in low or "authenticat" in low or "api key" in low:
            hint = "\n→ 명령 프롬프트에서 `claude`를 실행해 구독 계정으로 로그인해 주세요."
        elif "limit" in low:
            hint = "\n→ Claude 사용 한도에 걸렸어요. 잠시 후 다시 시도하세요."
        raise RuntimeError("Claude 검토 실패" + hint + "\n\n" + log[-1500:])
    if prompts.MARK_START in text and prompts.MARK_END in text:
        summary, rest = text.split(prompts.MARK_START, 1)
        improved = rest.split(prompts.MARK_END, 1)[0].strip()
    else:
        raise RuntimeError("Claude 답변에서 개선 프롬프트를 찾지 못했어요.\n\n" + text[-1500:])
    if len(improved) < 200:
        raise RuntimeError("Claude가 돌려준 프롬프트가 너무 짧아요.\n\n" + text[-1500:])
    return {"improved_prompt": improved, "summary_ko": summary.strip(), "log": log}


# ------------------------------------------------------------------ 로그인 (크롬으로 열기)
_login_proc = None  # 로그인 완료까지 프로세스를 살려두기 위한 참조


def login_status() -> str:
    """'로그인됨 · ...' / '로그인 안 됨' / '' (Claude Code 없음)."""
    exe = find_claude()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, timeout=30,
                           creationflags=NO_WINDOW)
        data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except Exception:  # noqa: BLE001
        return "확인 불가"
    if data.get("loggedIn"):
        who = data.get("subscriptionType") or data.get("authMethod") or ""
        return "로그인됨" + (f" · {who}" if who else "")
    return "로그인 안 됨"


def start_login(open_url, wait: float = 60.0) -> str:
    """`claude auth login --claudeai`(구독 계정)을 실행하고, 출력되는 로그인 주소를 open_url(주소)로 연다."""
    global _login_proc
    import re
    import threading

    exe = find_claude()
    if not exe:
        raise RuntimeError(SETUP_HELP)
    _login_proc = subprocess.Popen([exe, "auth", "login", "--claudeai"], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, stdin=subprocess.PIPE, creationflags=NO_WINDOW)
    found: list[str] = []
    done = threading.Event()
    ansi = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")

    def reader():
        for raw in iter(_login_proc.stdout.readline, b""):
            line = ansi.sub("", raw.decode("utf-8", "replace"))
            m = re.search(r"https://\S+", line)
            if m and not found and any(k in m.group(0) for k in ("oauth", "authorize", "login")):
                found.append(m.group(0).rstrip(".,)'\""))
                done.set()
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(wait)
    if not found:
        raise RuntimeError("Claude 로그인 주소를 받지 못했어요. 명령 프롬프트에서 `claude auth login`을 직접 실행해 주세요.")
    open_url(found[0])
    return found[0]


def qa(workdir: Path, result: str, sketch: str, refs: list[str], context_ko: str, prompt_used: str,
       model: str = "opus", timeout: int = 900) -> dict:
    """생성 결과 검수. 반환: {"verdict": "pass"|"revise", "issues_ko", "revision_prompt"}"""
    exe = find_claude()
    if not exe:
        raise RuntimeError(SETUP_HELP)
    request = prompts.qa_request_cli(result, sketch, refs, context_ko, prompt_used)
    args = [exe, "-p", "--output-format", "json", "--model", model, "--allowedTools", "Read"]
    try:
        r = subprocess.run(args, input=request.encode("utf-8"), cwd=workdir, capture_output=True,
                           timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude 검수가 {timeout // 60}분 안에 끝나지 않았어요.") from None
    out = r.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except json.JSONDecodeError:
        data = {}
    text = data.get("result", "") if isinstance(data, dict) else ""
    if r.returncode != 0 or data.get("is_error") or not text:
        raise RuntimeError("Claude 검수 실패\n\n" + (out + r.stderr.decode("utf-8", "replace"))[-1500:])
    verdict = "revise" if "VERDICT: REVISE" in text.upper() else "pass"
    body = text.split("\n", 1)[1] if text.upper().lstrip().startswith("VERDICT") else text
    revision = ""
    if prompts.REV_START in body and prompts.REV_END in body:
        issues, rest = body.split(prompts.REV_START, 1)
        revision = rest.split(prompts.REV_END, 1)[0].strip()
    else:
        issues = body
    if verdict == "revise" and not revision:
        verdict = "pass_with_notes"  # 문제는 적었지만 수정안을 못 받은 경우
    return {"verdict": verdict, "issues_ko": issues.strip(), "revision_prompt": revision}
