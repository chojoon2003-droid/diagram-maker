"""Claude Code 연결 테스터를 켜고 크롬(없으면 기본 브라우저)으로 연다. (기존 앱과 다른 포트 8502)"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import io_bridge

URL = "http://localhost:8502"
here = Path(__file__).parent
proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "claude_test_app.py",
                         "--server.port", "8502", "--server.headless", "true"], cwd=here)
for _ in range(120):
    try:
        urllib.request.urlopen(URL, timeout=1)
        break
    except Exception:  # noqa: BLE001
        time.sleep(0.5)
io_bridge.open_url(URL)
sys.exit(proc.wait())
