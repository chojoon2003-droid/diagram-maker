"""Codex 로그인 페이지를 크롬으로 연다 (codex_login_chrome.bat 에서 실행)."""
import time

import codex_bridge
import io_bridge

print("Codex 로그인 페이지를 크롬으로 여는 중...")
try:
    url = codex_bridge.start_login(io_bridge.open_url)
except RuntimeError as e:
    print(e)
    input("Enter를 누르면 닫혀요.")
    raise SystemExit(1)
print("크롬에서 ChatGPT 계정으로 로그인을 완료하세요.\n(크롬이 안 열리면 이 주소를 크롬에 붙여넣기)\n" + url)
proc = codex_bridge._login_proc
while proc.poll() is None:
    time.sleep(1)
print("\n" + (codex_bridge.login_status() or "완료"))
input("Enter를 누르면 닫혀요.")
