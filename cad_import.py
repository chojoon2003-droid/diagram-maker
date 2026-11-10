"""
CAD 파일 → 설계 자료 변환

- DXF (AutoCAD에서 '다른 이름으로 저장 → DXF'):
    도면을 흰 배경 PNG로 그리고, 도면 안의 글자(실명·면적·층 표기 등)를 뽑는다.
- SKP (스케치업, 시험 기능):
    .skp는 공개된 해석 도구가 없어 형상은 읽지 못한다. 대신 파일 안에 들어 있는
    미리보기 이미지와 읽을 수 있는 이름(컴포넌트·재질·태그·장면 이름 등)만 최대한 뽑는다.
"""

import io
import re


# ------------------------------------------------------------------ DXF
def dxf_to_png_and_text(data: bytes, max_px: int = 2400) -> tuple[bytes, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf import recover
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc, _auditor = recover.read(io.BytesIO(data))
    msp = doc.modelspace()
    _use_korean_font(doc)

    # 1) 도면 그리기 (흰 배경, 검정 선)
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_axes([0, 0, 1, 1])
    try:
        from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

        cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK)
        Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(msp, finalize=True)
    except TypeError:  # 구버전 ezdxf
        Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(msp, finalize=True)
    buf = io.BytesIO()
    fig.savefig(buf, dpi=max_px // 12, facecolor="white")
    plt.close(fig)

    # 2) 글자 뽑기 (TEXT / MTEXT / 블록 속성)
    texts: list[str] = []
    for e in msp.query("TEXT MTEXT"):
        try:
            t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
        except Exception:  # noqa: BLE001
            continue
        texts.append(t)
    for ins in msp.query("INSERT"):
        for att in getattr(ins, "attribs", []):
            texts.append(att.dxf.text)
    return buf.getvalue(), _clean_lines(texts)


# 한글이 네모(□)로 깨지지 않게, 모든 문자 스타일을 한글 지원 글꼴로 바꿔서 그린다
_KOREAN_FONTS = ["malgun.ttf", "NanumGothic.ttf", "AppleSDGothicNeo.ttc", "AppleGothic.ttf",
                 "NotoSansCJK-Regular.ttc", "NotoSansKR-Regular.otf", "wqy-zenhei.ttc"]


def _use_korean_font(doc) -> None:
    try:
        from ezdxf.fonts import fonts

        font = next((f for f in _KOREAN_FONTS if fonts.font_manager.has_font(f)), None)
        if not font:
            return
        for style in doc.styles:
            style.dxf.font = font
            if style.dxf.hasattr("bigfont"):
                style.dxf.discard("bigfont")
    except Exception:  # noqa: BLE001  (글꼴 교체 실패해도 도면은 그린다)
        pass


# ------------------------------------------------------------------ SKP (시험 기능)
_PNG_START, _PNG_END = b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82"
_JPG_START, _JPG_END = b"\xff\xd8\xff", b"\xff\xd9"
_SKIP_WORDS = ("Layer0", "Untagged", "Persp", "Default", "Material", "Component#", "Group#", "SketchUp",
               "Arial", "Tahoma", "Helvetica")


def skp_extract(data: bytes) -> tuple[bytes | None, str]:
    """(가장 큰 미리보기 이미지 bytes 또는 None, 읽을 수 있는 이름 목록 텍스트)"""
    images = []
    for start, end in ((_PNG_START, _PNG_END), (_JPG_START, _JPG_END)):
        pos = 0
        while (i := data.find(start, pos)) != -1:
            j = data.find(end, i)
            if j == -1:
                break
            images.append(data[i:j + len(end)])
            pos = j + len(end)
    preview = None
    if images:
        from PIL import Image

        for cand in sorted(images, key=len, reverse=True):
            try:
                Image.open(io.BytesIO(cand)).verify()
                preview = cand
                break
            except Exception:  # noqa: BLE001
                continue

    # 이름들: SketchUp(MFC)이 저장하는 유니코드 문자열 형식(FF FE FF + 길이 + UTF-16LE)을 찾아 읽는다
    words: list[str] = []
    for m in re.finditer(rb"\xff\xfe\xff", data):
        i = m.end()
        if i >= len(data):
            break
        n = data[i]
        i += 1
        if n == 0xFF:
            n = int.from_bytes(data[i:i + 2], "little")
            i += 2
        if not 2 <= n <= 120:
            continue
        try:
            word = data[i:i + 2 * n].decode("utf-16-le")
        except UnicodeDecodeError:
            continue
        if word.isprintable() and re.search(r"[가-힣A-Za-z]", word):
            words.append(word)
    words = [w for w in words if not any(k.lower() in w.lower() for k in _SKIP_WORDS)]
    return preview, _clean_lines(words, limit=150)


# ------------------------------------------------------------------ 공통
def _clean_lines(items: list[str], limit: int = 300) -> str:
    seen, out = set(), []
    for t in items:
        t = re.sub(r"\s+", " ", (t or "")).strip()
        if len(t) < 2 or t in seen or re.fullmatch(r"[\d.,\-+ ]+", t):
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return "\n".join(out)
