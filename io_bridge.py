"""
프로그램 공통 연결 통로 (포토샵 · 라이노 · 스케치업 · PPT 등 어떤 프로그램이든)

 - 입력: 클립보드 이미지 / 지정 폴더에 저장된 최신 이미지
 - 출력: 클립보드로 복사 / outputs 폴더 자동 저장 / PPT 파일 내보내기
앱은 내 컴퓨터에서 실행되므로 서버 쪽에서 OS 클립보드와 폴더를 직접 다룬다.
"""

import datetime as dt
import io
import os
import platform
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path

from PIL import Image, ImageGrab

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
SYSTEM = platform.system()


# ------------------------------------------------------------------ 입력
def grab_clipboard() -> bytes | None:
    """클립보드의 이미지(또는 복사한 이미지 파일)를 PNG bytes로. 없으면 None."""
    data = ImageGrab.grabclipboard()  # 실패 시 예외 → 호출부에서 표시
    if isinstance(data, list):  # 탐색기/Finder에서 파일 자체를 복사한 경우
        paths = [Path(p) for p in data if str(p).lower().endswith(IMG_EXT)]
        if not paths:
            return None
        data = Image.open(paths[0])
    if data is None:
        return None
    buf = io.BytesIO()
    data.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def latest_images(folder: Path, n: int = 15) -> list[Path]:
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMG_EXT]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:n]


# ------------------------------------------------------------------ 출력
def copy_to_clipboard(png: bytes) -> None:
    tmp = Path(tempfile.gettempdir()) / "diagram_clipboard.png"
    tmp.write_bytes(png)
    if SYSTEM == "Windows":
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
            f"[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{tmp}'))"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            check=True,
            creationflags=0x08000000,  # 콘솔 창 안 띄움
        )
    elif SYSTEM == "Darwin":
        subprocess.run(
            ["osascript", "-e", f'set the clipboard to (read (POSIX file "{tmp}") as «class PNGf»)'],
            check=True,
        )
    else:
        subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png", "-i", str(tmp)], check=True)


def copy_text(text: str) -> None:
    """텍스트(한글 포함)를 클립보드로."""
    if SYSTEM == "Windows":
        tmp = Path(tempfile.gettempdir()) / "diagram_prompt.txt"
        tmp.write_text(text, encoding="utf-8")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Content -Raw -Encoding UTF8 '{tmp}' | Set-Clipboard"],
            check=True,
            creationflags=0x08000000,
        )
    elif SYSTEM == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True,
                       env={**os.environ, "LANG": "en_US.UTF-8"})
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)


def write_images(folder: Path, items: list[tuple[str, bytes]]) -> None:
    """폴더를 비우고 [(파일명, bytes)]를 PNG로 저장 (ChatGPT에 끌어다 놓기용)."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        if old.is_file():
            old.unlink()
    for name, data in items:
        Image.open(io.BytesIO(data)).convert("RGB").save(folder / name, format="PNG")


def open_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if SYSTEM == "Windows":
        os.startfile(folder)  # type: ignore[attr-defined]
    elif SYSTEM == "Darwin":
        subprocess.run(["open", str(folder)])
    else:
        subprocess.run(["xdg-open", str(folder)])


def save_output(folder: Path, png: bytes, version: int) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"diagram_{dt.datetime.now():%Y%m%d_%H%M%S}_v{version}.png"
    path.write_bytes(png)
    return path


def build_pptx(items: list[tuple[bytes, str]]) -> bytes:
    """[(png, 캡션)] → 16:9 PPT, 한 장에 한 이미지(가운데 맞춤) + 하단 캡션."""
    from pptx import Presentation
    from pptx.util import Emu, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)  # 16:9
    W, H = prs.slide_width, prs.slide_height
    margin, cap_h = Emu(360000), Emu(500000)
    for png, caption in items:
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # 빈 슬라이드
        iw, ih = Image.open(io.BytesIO(png)).size
        box_w, box_h = W - 2 * margin, H - 2 * margin - cap_h
        scale = min(box_w / iw, box_h / ih)
        w, h = int(iw * scale), int(ih * scale)
        slide.shapes.add_picture(io.BytesIO(png), (W - w) // 2, margin + (box_h - h) // 2, w, h)
        tb = slide.shapes.add_textbox(margin, H - margin - cap_h, box_w, cap_h)
        tb.text_frame.text = caption
        tb.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


# ------------------------------------------------------------------ ChatGPT 열기 / 첨부 준비
def find_chrome() -> str | None:
    if SYSTEM == "Windows":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if base and (p := Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe").exists():
                return str(p)
    elif SYSTEM == "Darwin":
        if Path("/Applications/Google Chrome.app").exists():
            return "/Applications/Google Chrome.app"
    else:
        for name in ("google-chrome", "chromium", "chromium-browser"):
            if p := shutil.which(name):
                return p
    return None


def open_url(url: str, prefer_chrome: bool = True) -> str:
    """크롬이 있으면 크롬으로, 없으면 기본 브라우저로 연다. 사용한 브라우저 이름을 돌려줌."""
    chrome = find_chrome() if prefer_chrome else None
    if chrome:
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", chrome, url])
        else:
            subprocess.Popen([chrome, url])
        return "Chrome"
    webbrowser.open(url)
    return "기본 브라우저"


def open_desktop_app(name: str) -> None:
    """설치된 데스크탑 앱 실행 (윈도우: 시작 메뉴 등록 정보로 찾음). name 예: 'ChatGPT', 'Claude'."""
    if SYSTEM == "Windows":
        ps = (f"$a = Get-StartApps | Where-Object {{ $_.Name -eq '{name}' }} | Select-Object -First 1; "
              f"if (-not $a) {{ $a = Get-StartApps | Where-Object {{ $_.Name -like '{name}*' }} | Select-Object -First 1 }}; "
              "$a.AppID")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, creationflags=0x08000000)
        app_id = r.stdout.strip()
        if not app_id:
            raise RuntimeError(f"{name} 데스크탑 앱을 찾지 못했어요.")
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
    elif SYSTEM == "Darwin":
        subprocess.run(["open", "-a", name], check=True)
    else:
        raise RuntimeError(f"이 운영체제에는 {name} 데스크탑 앱이 없어요.")


def open_chatgpt_desktop() -> None:
    open_desktop_app("ChatGPT")


def grab_text() -> str:
    """클립보드의 텍스트(한글 포함)를 읽는다."""
    if SYSTEM == "Windows":
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-Clipboard -Raw"],
            capture_output=True, creationflags=0x08000000,
        )
        return r.stdout.decode("utf-8", errors="replace")
    if SYSTEM == "Darwin":
        return subprocess.run(["pbpaste"], capture_output=True, env={**os.environ, "LANG": "en_US.UTF-8"}
                              ).stdout.decode("utf-8", errors="replace")
    return subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, check=True
                          ).stdout.decode("utf-8", errors="replace")


def copy_files(paths: list[Path]) -> None:
    """파일 여러 개를 '파일 복사' 형태로 클립보드에 (탐색기에서 Ctrl+C 한 것과 같음)."""
    if SYSTEM == "Windows":
        quoted = ",".join(f"'{p}'" for p in paths)
        subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", f"Set-Clipboard -Path {quoted}"],
                       check=True, creationflags=0x08000000)
    elif SYSTEM == "Darwin":
        files = ", ".join(f'POSIX file "{p}"' for p in paths)
        subprocess.run(["osascript", "-e", f"set the clipboard to {{{files}}}"], check=True)
    else:
        raise RuntimeError("이 운영체제에서는 파일 복사를 지원하지 않아요.")


def make_board(sketch: bytes, refs: list[bytes], projects: list[bytes] | None = None) -> bytes:
    """스케치(왼쪽, 크게) + 레퍼런스·내 설계 도면(오른쪽, 작게)을 라벨과 함께 한 장으로 합침."""
    side = [(b, f"REF {i} = STYLE ONLY", "blue") for i, b in enumerate(refs, 1)]
    side += [(b, f"PROJECT {i} = FACTS", "green") for i, b in enumerate(projects or [], 1)]
    from PIL import ImageDraw, ImageFont

    H, gap, label_h = 1400, 24, 56
    sk = Image.open(io.BytesIO(sketch)).convert("RGB")
    sk = sk.resize((max(1, int(sk.width * H / sk.height)), H))
    col_w = 600 if side else 0
    ref_imgs = []
    if side:
        slot_h = (H - gap * (len(side) - 1)) // len(side) - label_h
        for b, label, color in side:
            im = Image.open(io.BytesIO(b)).convert("RGB")
            im.thumbnail((col_w, max(80, slot_h)))
            ref_imgs.append((im, label, color))
    W = sk.width + (gap + col_w if side else 0)
    board = Image.new("RGB", (W + 2 * gap, H + label_h + 2 * gap), "white")
    d = ImageDraw.Draw(board)
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:  # 구버전 Pillow
        font = ImageFont.load_default()
    d.text((gap, gap), "SKETCH = CONTENT", fill="red", font=font)
    board.paste(sk, (gap, gap + label_h))
    y, x = gap, gap + sk.width + gap
    for im, label, color in ref_imgs:
        d.text((x, y), label, fill=color, font=font)
        board.paste(im, (x, y + label_h))
        y += label_h + im.height + gap
    buf = io.BytesIO()
    board.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ 데스크탑 알림
_TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$t = [Security.SecurityElement]::Escape($env:NT_TITLE)
$b = [Security.SecurityElement]::Escape($env:NT_BODY)
$img = ''
if ($env:NT_IMG) { $img = "<image placement='hero' src='" + [Security.SecurityElement]::Escape($env:NT_IMG) + "'/>" }
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text>$img</binding></visual><audio src='ms-winsoundevent:Notification.Default'/></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notify(title: str, body: str, image: Path | None = None) -> None:
    """윈도우/맥 데스크탑 알림 (오른쪽 아래 알림 + 소리). 실패해도 앱은 계속 동작."""
    try:
        if SYSTEM == "Windows":
            env = {**os.environ, "NT_TITLE": title, "NT_BODY": body,
                   "NT_IMG": str(Path(image).resolve()) if image else ""}
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _TOAST_PS],
                             env=env, creationflags=0x08000000)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["osascript", "-e", "on run argv", "-e",
                              'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"',
                              "-e", "end run", title, body])
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, body])
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ 설계 글 파일에서 텍스트 추출
def extract_text(name: str, data: bytes) -> str:
    """.txt/.md/.pdf/.docx 에서 글자만 뽑는다 (설계 논리·프로그램 설명용)."""
    low = name.lower()
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if low.endswith(".docx"):
        import docx

        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs).strip()
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace").strip()
