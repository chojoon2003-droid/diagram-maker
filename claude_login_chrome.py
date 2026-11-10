"""Claude Code 로그인 페이지를 크롬으로 연다 (claude_login_chrome.bat 에서 실행)."""
import time

import claude_cli
import io_bridge

print("Claude Code 로그인 페이지를 크롬으로 여는 중...")
try:
    url = claude_cli.start_login(io_bridge.open_url)
except RuntimeError as e:
    print(e)
    input("Enter를 누르면 닫혀요.")
    raise SystemExit(1)
print("크롬에서 Claude 구독 계정으로 로그인을 완료하세요.\n(크롬이 안 열리면 이 주소를 크롬에 붙여넣기)\n" + url)
print("\n로그인 후 이 창에 코드를 붙여넣으라는 안내가 나오면, 코드를 붙여넣고 Enter.")
proc = claude_cli._login_proc
while proc.poll() is None:
    time.sleep(1)
print("\n" + (claude_cli.login_status() or "완료"))
input("Enter를 누르면 닫혀요.")
