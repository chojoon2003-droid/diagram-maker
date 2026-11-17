# 앱에서 Codex · Claude Code 연결하기 (요약)

내 프로그램이 **구독 계정(API 키 없음)**으로 Codex(ChatGPT)와 Claude Code를 자동 실행하는 방법.
핵심: 앱이 CLI를 **subprocess로 실행**하고, 프롬프트는 **stdin**으로 넣고, 결과는 **파일/JSON**으로 받는다.

---

## 1. 설치 · 로그인 (컴퓨터마다 한 번)
| 도구 | 설치 | 로그인 | 확인 |
|---|---|---|---|
| Node.js | `winget install -e --id OpenJS.NodeJS.LTS` | – | `node --version` (18 이상) |
| Codex | `npm.cmd install -g @openai/codex` | `codex login` (ChatGPT 개인 계정) | `codex login status` |
| Claude Code | PowerShell: `irm https://claude.ai/install.ps1 \| iex` | `claude auth login --claudeai` | `claude auth status --json` → `loggedIn` |

**Windows 주의**
- `npm` 대신 **`npm.cmd`** 사용 (PowerShell 실행 정책 오류 방지)
- 설치 직후 명령이 안 잡히면: 새 창을 열거나 아래 위치를 직접 찾는다
  - Codex: `%APPDATA%\npm\codex.cmd`
  - Claude: `%USERPROFILE%\.local\bin\claude.exe` (사용자 PATH에 추가)
- 로그인 주소를 **크롬**으로 열려면: `codex login` / `claude auth login` 출력에서 `https://...` 주소를 읽어 크롬으로 직접 연다

---

## 2. Codex 실행 (이미지 생성 · 작업)
```
codex exec --skip-git-repo-check --sandbox workspace-write \
  -m gpt-6-astra -c model_reasoning_effort=low \
  -i sketch.png -i ref.png --json -
```
- 프롬프트는 **stdin**으로 (`-` = stdin에서 읽기), `cwd` = 작업 폴더
- 생각 수준: `low` / `medium` / `high` (low가 빠르고 사용량 적음)
- `--json` 출력의 `thread_id`(또는 `session_id`)를 저장 → 수정 요청은
  `codex exec resume <id> ... -` 로 같은 대화 이어가기
- 이미지 생성 프롬프트 끝에 붙이는 지시 (토큰 절약 + 결과 찾기 쉽게):
  ```
  Use the built-in image generation tool ($imagegen) with the attached image(s).
  Do not write code, install anything or call external APIs.
  Generate once. Do not open, inspect or re-check the image.
  Save the final image as `out.png` in the current directory, then print `SAVED: out.png`.
  ```
- 결과 찾는 순서: ① 지정한 파일명 → ② 출력의 `SAVED:` 줄 → ③ 작업 폴더의 새 PNG → ④ `~/.codex/generated_images`
- 오류 메시지 판별: `login/401` → 로그인 필요, `model not found` → 모델명, `usage limit` → 한도

## 3. Claude Code 실행 (검토 · 검수 · 질문)
```
claude -p --output-format json --model opus --allowedTools Read
```
- 프롬프트는 **stdin**, 이미지는 작업 폴더에 두고 프롬프트에 **파일 경로**를 적으면 Read로 직접 본다
  (큰 이미지는 긴 변 1568px 정도로 줄여서 넣기)
- 출력 JSON 주요 항목: `result`(답변), `is_error`, `usage`(토큰), `total_cost_usd`(API 환산 금액, 구독이면 청구 안 됨), `permission_denials`, `session_id`
- 권한: `--allowedTools Read` = 읽기만. 파일 쓰기가 필요하면 `Read,Write` 처럼 필요한 것만 추가
- 답변에서 원하는 부분만 뽑으려면 프롬프트에 표시를 요구: 예) `<<<PROMPT>>> ... <<<END>>>`, `VERDICT: PASS/REVISE`

## 4. Python 기본 틀
```python
import subprocess, json, platform
NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0   # 검은 창 안 뜨게

def run_cli(args, prompt, cwd, timeout=900):
    r = subprocess.run(args, input=prompt.encode("utf-8"), cwd=cwd, capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# Claude Code
code, out, err = run_cli(["claude", "-p", "--output-format", "json", "--model", "sonnet"], "질문", ".")
data = json.loads(out.strip().splitlines()[-1]); print(data["result"], data["usage"])

# Codex
code, out, err = run_cli(["codex", "exec", "--skip-git-repo-check", "-m", "gpt-6-astra",
                          "-c", "model_reasoning_effort=low", "--json", "-"], "Reply with exactly: OK", ".")
```
- 경로는 `shutil.which("codex")` → 없으면 위 1번의 위치를 직접 확인 (Windows의 `.cmd`도 그대로 실행 가능)
- 연결 테스트: 각각 `Reply with exactly: OK` 를 보내 응답에 OK가 있는지 확인

---

## 5. 사용 기록 · 개인정보
- 질문·답변·토큰 기록은 **실행한 컴퓨터에만** 저장
  - Claude Code: `%USERPROFILE%\.claude\projects\**\*.jsonl` (assistant 항목의 `message.usage`)
  - Codex: `%USERPROFILE%\.codex\sessions`
- claude.ai · ChatGPT 웹 대화 목록에는 **안 뜸** → 웹에서는 전체 구독 사용량만 보임
- 구독 사용 한도는 웹/앱/CLI가 **공유**
- 학교·회사 계정은 관리자가 사용 기록을 볼 수 있으니 **개인 계정으로 로그인**
- 브라우저(claude.ai/ChatGPT 웹)를 자동 조작하는 방식은 쓰지 않음 (약관) → 공식 CLI만 사용
