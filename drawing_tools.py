"""
원본 선 고정 합성 (평면·단면 리터칭용)

AI가 색·질감·그림자를 입힌 결과 위에 원본 도면의 선을 다시 겹쳐서,
AI가 선을 조금 틀어도 최종본의 선은 원본과 똑같게 만든다.

1) 원본에서 '선'(어두운 픽셀)만 뽑는다            → line_mask
2) 원본을 AI 결과의 위치·크기에 맞춘다 (자동 정렬)  → align_to
3) 결과 위에 원본 선을 덮는다                      → lock_lines
"""

import io

import numpy as np
from PIL import Image, ImageFilter


def _load(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def line_mask(img: Image.Image, threshold: int = 150, thicken: int = 0) -> Image.Image:
    """어두운 픽셀(선) = 255, 나머지 = 0 인 마스크. threshold가 높을수록 옅은 선까지 잡는다."""
    gray = np.asarray(img.convert("L"))
    mask = Image.fromarray(((gray < threshold) * 255).astype("uint8"))
    if thicken > 0:
        mask = mask.filter(ImageFilter.MaxFilter(thicken * 2 + 1))
    return mask


def align_to(original: Image.Image, result: Image.Image) -> tuple[Image.Image, str]:
    """원본을 결과 이미지 크기·위치에 맞춰 변형. (정렬된 원본, 사용한 방법 설명)"""
    W, H = result.size
    try:
        import cv2

        o = cv2.cvtColor(np.asarray(original), cv2.COLOR_RGB2GRAY)
        r = cv2.cvtColor(np.asarray(result), cv2.COLOR_RGB2GRAY)
        # 크기를 비슷하게 맞춘 뒤 특징점 매칭 → 회전·이동·균일 배율만 허용하는 정렬
        pre = W / original.width
        o_s = cv2.resize(o, (W, max(1, int(original.height * pre))))
        orb = cv2.ORB_create(4000)
        k1, d1 = orb.detectAndCompute(o_s, None)
        k2, d2 = orb.detectAndCompute(r, None)
        if d1 is not None and d2 is not None and len(k1) > 20 and len(k2) > 20:
            matches = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda m: m.distance)
            matches = matches[:500]
            if len(matches) >= 20:
                src = np.float32([k1[m.queryIdx].pt for m in matches])
                dst = np.float32([k2[m.trainIdx].pt for m in matches])
                M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
                if M is not None and inl is not None and int(inl.sum()) >= 20:
                    scale = float(np.hypot(M[0, 0], M[1, 0]))
                    if 0.7 < scale < 1.4:
                        warped = cv2.warpAffine(np.asarray(original.resize(o_s.shape[::-1])), M, (W, H),
                                                borderValue=(255, 255, 255))
                        return Image.fromarray(warped), f"자동 정렬 (일치점 {int(inl.sum())}개)"
    except Exception:  # noqa: BLE001  (OpenCV가 없거나 정렬 실패 → 다음 방법)
        pass
    # 단순 맞춤: 비율 유지하며 가운데 배치 (AI가 같은 구도로 그렸다고 가정)
    canvas = Image.new("RGB", (W, H), "white")
    ratio = min(W / original.width, H / original.height)
    fit = original.resize((max(1, int(original.width * ratio)), max(1, int(original.height * ratio))))
    canvas.paste(fit, ((W - fit.width) // 2, (H - fit.height) // 2))
    # 2차: 전체 구조(윤곽 세기)를 맞추는 정렬(ECC) — 특징점이 적은 단순한 모델 뷰·렌더에 강함
    try:
        import cv2

        def grad(x):
            x = cv2.GaussianBlur(x, (5, 5), 0).astype(np.float32)
            g = cv2.magnitude(cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3))
            return cv2.GaussianBlur(g, (9, 9), 0)

        g_res = cv2.cvtColor(np.asarray(result), cv2.COLOR_RGB2GRAY)
        g_inp = cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2GRAY)
        warp = np.eye(2, 3, dtype=np.float32)
        prev_f, cc = None, 0.0
        for width in (200, 400, 800):  # 거칠게 → 정밀하게 단계적으로 맞춤
            f = min(1.0, width / W)
            if prev_f is not None:
                warp[:, 2] *= f / prev_f
            small = (max(1, int(W * f)), max(1, int(H * f)))
            cc, warp = cv2.findTransformECC(grad(cv2.resize(g_res, small)), grad(cv2.resize(g_inp, small)), warp,
                                            cv2.MOTION_AFFINE,
                                            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 150, 1e-6), None, 5)
            prev_f = f
        scale = float(np.sqrt(abs(np.linalg.det(warp[:, :2]))))
        if cc > 0.4 and 0.7 < scale < 1.4:
            warp[:, 2] /= prev_f
            out = cv2.warpAffine(np.asarray(canvas), warp, (W, H), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                                 borderValue=(255, 255, 255))
            return Image.fromarray(out), f"자동 정렬 (구조 일치 {cc:.2f})"
    except Exception:  # noqa: BLE001
        pass
    return canvas, "단순 맞춤 (자동 정렬 실패 — 위치가 어긋나면 투명도를 낮추거나 끄세요)"


def lock_lines(result_png: bytes, original_png: bytes, opacity: float = 1.0, threshold: int = 150,
               thicken: int = 0) -> tuple[bytes, str]:
    """AI 결과 위에 원본 선을 덮은 이미지(PNG)와 정렬 방법 설명을 돌려준다."""
    result = _load(result_png)
    aligned, how = align_to(_load(original_png), result)
    mask = line_mask(aligned, threshold, thicken)
    if opacity < 1.0:
        mask = mask.point(lambda v: int(v * opacity))
    out = Image.composite(aligned, result, mask)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue(), how


# ------------------------------------------------------------------ 렌더링: 재료 색 코딩 맵
def map_colors(png: bytes, max_colors: int = 12, min_share: float = 0.01) -> list[tuple[str, float]]:
    """재료 색 코딩 맵에서 주요 단색들을 뽑는다. [(#rrggbb, 면적 비율)] — 흰/검정 배경·선은 제외."""
    img = _load(png)
    img.thumbnail((400, 400))
    q = img.quantize(colors=max_colors * 2, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    out: list[tuple[str, float]] = []
    for c, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        share = c / total
        if share < min_share:
            continue
        if max(r, g, b) > 238 and min(r, g, b) > 238:  # 흰 배경
            continue
        if max(r, g, b) < 30:  # 검정 선
            continue
        hexc = f"#{r:02x}{g:02x}{b:02x}"
        # 거의 같은 색은 하나로
        if any(sum(abs(int(hexc[i:i + 2], 16) - int(h[i:i + 2], 16)) for i in (1, 3, 5)) < 40 for h, _ in out):
            continue
        out.append((hexc, round(share * 100, 1)))
        if len(out) >= max_colors:
            break
    return out


# ------------------------------------------------------------------ 렌더링: 형태 비교 (윤곽선 차이)
def edge_diff(input_png: bytes, result_png: bytes) -> tuple[bytes, float, str]:
    """입력(모델 뷰)과 결과의 윤곽선을 정렬·비교한 이미지.
    빨강 = 모델에는 있는데 결과에서 사라진 윤곽, 파랑 = 결과에 새로 생긴 윤곽.
    반환: (비교 이미지 PNG, 사라진 윤곽 비율 %, 정렬 방법)"""
    import cv2

    result = _load(result_png)
    aligned, how = align_to(_load(input_png), result)
    a = cv2.cvtColor(np.asarray(aligned), cv2.COLOR_RGB2GRAY)
    r = cv2.cvtColor(np.asarray(result), cv2.COLOR_RGB2GRAY)
    ea = cv2.Canny(cv2.GaussianBlur(a, (3, 3), 0), 60, 160)
    er = cv2.Canny(cv2.GaussianBlur(r, (3, 3), 0), 60, 160)
    k = np.ones((7, 7), np.uint8)  # 몇 픽셀 어긋남은 허용
    missing = (ea > 0) & (cv2.dilate(er, k) == 0)
    added = (er > 0) & (cv2.dilate(ea, k) == 0)
    # 잔잔한 질감·첨경 노이즈를 줄이려고 작은 조각(짧은 선)은 지운다
    def drop_small(mask, min_px=25):
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        keep = np.zeros(n, bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
        return keep[lab]

    missing, added = drop_small(missing), drop_small(added)
    base = (np.asarray(result).astype(np.float32) * 0.35 + 255 * 0.65).astype(np.uint8)  # 결과를 옅게
    out = base.copy()
    out[cv2.dilate(added.astype(np.uint8), np.ones((2, 2), np.uint8)) > 0] = (40, 110, 255)
    out[cv2.dilate(missing.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0] = (230, 30, 30)
    pct = round(100.0 * missing.sum() / max(1, (ea > 0).sum()), 1)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="PNG")
    return buf.getvalue(), pct, how
