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
    except Exception:  # noqa: BLE001  (OpenCV가 없거나 정렬 실패 → 단순 맞춤)
        pass
    # 단순 맞춤: 비율 유지하며 가운데 배치 (AI가 같은 구도로 그렸다고 가정)
    canvas = Image.new("RGB", (W, H), "white")
    ratio = min(W / original.width, H / original.height)
    fit = original.resize((max(1, int(original.width * ratio)), max(1, int(original.height * ratio))))
    canvas.paste(fit, ((W - fit.width) // 2, (H - fit.height) // 2))
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
