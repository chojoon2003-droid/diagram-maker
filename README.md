# 건축 다이어그램 에이전트

레퍼런스(이미지·느낌 텍스트) + 다이어그램 설명 + 내 스케치를 넣으면,
프롬프트 작성 → Claude 검토 → OpenAI(Codex / GPT-6 Astra)로 다이어그램 이미지 생성까지 한 번에 진행하는 로컬 앱.

## 다른 컴퓨터에서 받기
**git 사용 (추천)** — 명령 프롬프트(cmd)에서:
```bat
cd %USERPROFILE%\Documents
git clone https://github.com/chojoon2003-droid/diagram-maker.git
```
처음엔 GitHub 로그인 창이 떠요 → **Sign in with your browser** → 본인 계정으로 로그인.

**업데이트 받기**:
```bat
cd %USERPROFILE%\Documents\diagram-maker
git pull
```
API 키 파일과 결과물(`outputs/`)은 git이 관리하지 않아 업데이트해도 그대로 남아요.

**git 없이**: 저장소 페이지 → 초록색 **Code** 버튼 → **Download ZIP** → 압축 풀기

## 처음 실행
자세한 내용은 [`사용법.txt`](사용법.txt) 참고.
1. 파이썬 설치 (설치 화면에서 "Add python.exe to PATH" 체크)
2. `make_desktop_shortcut.bat` 더블클릭 → 바탕화면 "Diagram Agent" 아이콘 생성
3. 아이콘 더블클릭 → 크롬에서 앱이 열림

원클릭 자동(Codex + Claude Code)을 쓰려면:
- Node.js 설치 → `npm install -g @openai/codex` → `codex_login_chrome.bat`
- Claude Code 설치 → `claude_login_chrome.bat`

## 보안
API 키(`api_key.txt`, `gemini_key.txt`, `claude_key.txt`)와 생성 결과(`outputs/`, `inbox/`, `to_chatgpt/`, `to_codex/`)는
`.gitignore`로 저장소에 올라가지 않아요. 새 컴퓨터에서는 앱 사이드바에 키를 다시 넣고 "저장"을 누르세요.

## 파일 구성
| 파일 | 역할 |
|---|---|
| `app.py` | 앱 화면 (Streamlit) |
| `prompts.py` | ChatGPT/Codex/Claude용 프롬프트 생성 |
| `claude_cli.py` / `claude_review.py` | Claude 검토 (Claude Code 구독 / Claude API) |
| `codex_bridge.py` | Codex(GPT-6 Astra) 이미지 생성 |
| `llm.py` / `keywords.py` | Gemini·OpenAI 분석, 키워드 추천 사전 |
| `io_bridge.py` | 클립보드·폴더·크롬·PPT 연결 |
| `launch.py`, `*.bat`, `run_mac.command` | 실행·로그인 도우미 |
