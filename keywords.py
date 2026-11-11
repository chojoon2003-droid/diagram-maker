"""
스타일 추천 키워드 사전 (API 없이 동작하는 기본 추천).
문장을 구절로 나눈 뒤, 각 구절에 TRIGGERS가 들어 있으면 그 구절을 대체할 키워드를 추천한다.
키워드 표기: "한국어 · english"  (영어 부분은 이미지 생성 프롬프트용)
자주 쓰는 표현이 있으면 자유롭게 추가하세요.
"""

import re

GROUPS = [
    (["손그림", "손으로", "스케치", "드로잉", "연필", "펜", "아날로그", "hand", "sketch"],
     ["손그림 선 · hand-drawn line", "연필 질감 · pencil texture", "잉크 펜 선 · ink pen linework",
      "느슨한 스케치 선 · loose sketch strokes", "트레이싱지 · tracing paper", "마커 음영 · marker shading"]),
    (["따뜻", "포근", "아늑", "웜", "warm"],
     ["따뜻한 색감 · warm color palette", "베이지 종이 배경 · warm beige paper", "부드러운 햇빛 · soft warm light",
      "흙빛 톤 · earthy tones"]),
    (["시원", "차가", "쿨", "청량", "cool"],
     ["차가운 색감 · cool blue-grey palette", "맑은 하늘색 강조 · light blue accent", "선명한 대비 · crisp contrast"]),
    (["수채", "물감", "번짐", "watercolor"],
     ["수채화 워시 · watercolor wash", "색 번짐 · soft color bleed", "종이 결 · paper grain", "파스텔 톤 · pastel tones"]),
    (["미니멀", "깔끔", "심플", "단순", "정돈", "모던", "minimal", "clean"],
     ["미니멀 플랫 · minimal flat vector", "균일한 얇은 선 · thin uniform lines", "넉넉한 여백 · generous white space",
      "단색+포인트 컬러 · monochrome with one accent", "그림자 없음 · no shadows", "산세리프 라벨 · sans-serif labels"]),
    (["부드러", "은은", "잔잔", "soft"],
     ["낮은 채도 · desaturated colors", "부드러운 그라데이션 · soft gradients", "옅은 그림자 · subtle shadows"]),
    (["차분", "고급", "무채", "모노", "흑백", "톤다운", "세련", "muted", "elegant"],
     ["톤다운 색감 · muted tones", "무채색+포인트 · greyscale with subtle accent", "모노크롬 · monochrome",
      "가는 세리프 라벨 · elegant thin serif labels"]),
    (["컬러", "화사", "밝", "팝", "생동", "경쾌", "colorful", "vivid"],
     ["선명한 원색 · vivid flat colors", "대담한 색 블록 · color blocking", "경쾌한 그래픽 · playful pop graphics"]),
    (["액소", "아이소", "입체", "axo", "iso", "3d"],
     ["액소노메트릭 · axonometric view", "아이소메트릭 · isometric 30°", "반투명 매스 · transparent massing",
      "숨은선 점선 · dashed hidden lines"]),
    (["분해", "층별", "exploded"],
     ["분해 액소 · exploded axonometric", "층별 분리 · floor-by-floor separation", "수직 연결 점선 · vertical dashed guides"]),
    (["개념", "과정", "프로세스", "매스", "변형", "단계", "concept", "process", "massing"],
     ["단계별 매스 변화 · step-by-step massing sequence", "번호 매긴 단계 · numbered steps",
      "변형 화살표 · bold transformation arrows", "밀기/당기기/회전 · push / pull / rotate operations"]),
    (["동선", "흐름", "이동", "circulation", "flow"],
     ["동선 화살표 · circulation arrows", "점선 흐름 · dotted flow lines", "강조색 동선 · accent-colored path"]),
    (["프로그램", "용도", "조닝", "공간 구성", "program", "zoning"],
     ["용도별 색 구분 · color-coded program zones", "반투명 볼륨 · translucent program volumes", "범례 박스 · legend box"]),
    (["환경", "빛", "바람", "일조", "채광", "환기", "친환경", "sun", "wind"],
     ["태양 궤적 · sun path arc", "바람 흐름 화살표 · wind flow arrows", "채광 광선 · daylight rays",
      "빗물 순환 · rainwater cycle", "온/냉 그라데이션 화살표 · warm/cool gradient arrows"]),
    (["콜라주", "사진", "포토", "텍스처", "collage"],
     ["포토 콜라주 · photo collage", "오려붙인 질감 · cut-out textures", "리소그래프 입자 · risograph grain", "망점 · halftone"]),
    (["사람", "나무", "첨경", "조경", "활기", "people", "tree"],
     ["실루엣 인물 · silhouette people", "선화 나무 · line-art trees", "최소한의 첨경 · minimal entourage",
      "컬러 첨경 · colored entourage"]),
    (["단면", "평면", "입면", "section", "plan"],
     ["단면 투시 · section perspective", "절단면 검정 포셰 · solid black poché", "해치 패턴 · hatch patterns",
      "지반선 강조 · bold ground line"]),
    (["선명", "날카", "또렷", "정확", "sharp"],
     ["선명한 벡터 선 · crisp vector lines", "높은 대비 · high contrast", "정밀한 선 위계 · precise line weight hierarchy"]),
]

# 느낌·감정 표현 → 비슷한 느낌의 건축적 언어 (공간·빛·재료·매스·비례·리듬)
ARCH_LANG = [
    (["고요", "조용", "정적", "평온", "평화", "잔잔", "명상", "차분", "calm", "quiet"],
     ["절제된 여백 · restrained void", "수평적 연속성 · horizontal continuity", "확산광 · diffused light",
      "깊은 처마 그림자 · deep eave shadow", "낮은 채도 재료 · muted material palette"]),
    (["웅장", "거대", "압도", "장엄", "기념", "monument", "grand"],
     ["기념비적 스케일 · monumental scale", "대칭 축 · strong symmetrical axis", "높은 층고 · double-height void",
      "묵직한 기단 · heavy plinth", "역광 실루엣 · backlit silhouette"]),
    (["가벼", "떠있", "떠 있", "부유", "경쾌", "날렵", "light", "float"],
     ["부유하는 매스 · floating volume", "얇은 슬래브 · thin cantilevered slab", "가는 기둥 · slender pilotis",
      "투명한 외피 · transparent skin", "그림자 없는 하부 · lifted ground plane"]),
    (["무거", "단단", "묵직", "견고", "솔리드", "heavy", "solid"],
     ["매스의 무게감 · massive volume", "두꺼운 벽체 · thick poché walls", "깊은 개구부 · deep-set openings",
      "육중한 기단 · grounded base"]),
    (["개방", "열린", "트인", "시원하게", "확장", "open"],
     ["열린 평면 · open plan", "시각적 투과성 · visual permeability", "실내외 연속 · indoor-outdoor continuity",
      "필로티 · pilotis", "긴 시선축 · long sightline"]),
    (["아늑", "포근", "따뜻", "감싸", "숨은", "은신", "안락", "cozy"],
     ["둘러싸인 중정 · enclosed courtyard", "낮은 천장 · compressed low ceiling", "켜 공간 · layered thresholds",
      "따뜻한 목재 · warm timber", "작은 알코브 · intimate alcove"]),
    (["자연", "녹색", "숲", "초록", "식물", "정원", "친환경", "green", "nature"],
     ["바이오필릭 · biophilic", "녹지 테라스 · planted terraces", "실내 정원 · interior garden",
      "자연 채광·환기 · daylight & cross ventilation", "흙과 목재 · earth & timber"]),
    (["도시", "복잡", "활기", "북적", "다양", "번화", "urban", "busy"],
     ["도시적 켜 · urban layering", "혼합 용도 · mixed-use stacking", "활성화된 저층부 · active ground floor",
      "다공성 매스 · porous massing", "교차하는 동선 · intersecting circulation"]),
    (["리듬", "반복", "패턴", "규칙", "질서", "모듈", "rhythm", "pattern"],
     ["반복되는 리듬 · rhythmic repetition", "모듈 그리드 · modular grid", "열주 · colonnade",
      "프레임 반복 · repeated frames", "비례 체계 · proportional system"]),
    (["투명", "유리", "비치", "반투명", "transparent", "glass"],
     ["투명성 · transparency", "반투명 켜 · translucent layers", "유리 볼륨 · glass volume", "빛의 투과 · light filtering"]),
    (["거친", "러프", "투박", "날것", "원초", "raw", "rough"],
     ["노출 콘크리트 · raw exposed concrete", "거친 질감 · rough tactile texture", "브루탈리즘 · brutalist",
      "재료의 솔직함 · honest materiality"]),
    (["유기", "곡선", "흐르", "유연", "부드러운 형태", "organic", "curve"],
     ["유기적 곡선 · organic curves", "흐르는 공간 · flowing space", "연속 곡면 · continuous surface", "지형적 형태 · landform"]),
    (["기하", "각진", "직선", "반듯", "명쾌", "geometric"],
     ["순수 기하 · pure geometry", "명확한 직교 그리드 · strict orthogonal grid", "날카로운 모서리 · crisp edges",
      "볼륨의 조합 · additive volumes"]),
    (["오래", "시간", "역사", "전통", "옛", "기억", "heritage"],
     ["시간의 흔적 · patina of time", "켜켜이 쌓인 역사 · historical layering", "전통 지붕선 · traditional roofline",
      "재생 · adaptive reuse"]),
    (["미래", "첨단", "디지털", "하이테크", "실험", "future"],
     ["파라메트릭 형태 · parametric form", "하이테크 구조 노출 · high-tech exposed structure", "디지털 패턴 · digital patterning"]),
    (["빛", "밝", "환한", "햇살", "채광", "light"],
     ["빛의 우물 · light well", "천창 · skylight", "빛과 그림자 대비 · chiaroscuro", "반사광 · reflected light"]),
    (["연결", "이어", "관계", "소통", "만남", "connect"],
     ["공간의 연결 · spatial connection", "브리지 · bridge link", "공유 마당 · shared court", "시선 교차 · crossing views"]),
    (["모이", "모임", "모여", "함께", "커뮤니티", "공유", "소통", "어울", "gather", "community"],
     ["공유 마당 · shared courtyard", "계단식 광장 · stepped plaza", "공용 라운지 · communal lounge",
      "열린 마루 · open maru platform", "머무는 가장자리 · inhabited edges"]),
    (["시적", "감성", "서정", "낭만", "몽환", "poetic", "dreamy"],
     ["빛과 그림자의 시 · poetic light and shadow", "느린 시퀀스 · slow spatial sequence", "물의 반사 · reflecting water",
      "프레임된 풍경 · framed view", "안개 같은 빛 · hazy atmospheric light"]),
    (["경계", "사이", "중간", "전이", "threshold"],
     ["전이 공간 · transitional space", "켜진 경계 · layered boundary", "회랑 · arcade", "반외부 공간 · semi-outdoor space"]),
]

# 평면·단면 리터칭용 표현 (문장에 해당 단어가 있으면 추천)
GROUPS += [
    (["포셰", "벽 채움", "검정 벽", "흑백", "poche"],
     ["절단 벽 검정 포셰 · solid black poché walls", "회색 포셰 · grey poché walls", "선 굵기 위계 · line weight hierarchy"]),
    (["실별", "조닝", "색 구분", "공간 구분", "zoning"],
     ["실별 파스텔 채색 · pastel room fills", "용도별 색 구분 · color-coded program zones", "공용·사적 위계 색 · public-private color gradient"]),
    (["가구", "인테리어", "furniture"],
     ["선화 가구 · line-art furniture", "회색 톤 가구 · grey-toned furniture", "최소 가구 배치 · minimal furniture layout"]),
    (["바닥", "재질", "마감", "floor"],
     ["목재 바닥 패턴 · timber floor pattern", "타일 그리드 · tile grid", "콘크리트 질감 · concrete texture"]),
    (["그림자", "깊이", "입체감", "shadow"],
     ["부드러운 그림자 · soft drop shadows", "45° 그림자 · 45-degree cast shadows", "앰비언트 오클루전 · ambient occlusion"]),
    (["지반", "땅", "지형", "흙", "ground"],
     ["지반 해치 · ground hatch", "흙 질감 단면 · soil texture in section", "지반선 강조 · bold ground line"]),
    (["하늘", "배경", "sky"],
     ["옅은 하늘 그라데이션 · soft sky gradient", "흰 배경 · plain white background", "원경 건물 회색 · grey background buildings"]),
]

PLAN_DEFAULT = ["절단 벽 검정 포셰 · solid black poché walls", "실별 파스텔 채색 · pastel room fills",
                "선화 가구 · line-art furniture", "목재 바닥 패턴 · timber floor pattern",
                "부드러운 그림자 · soft drop shadows", "선화 나무 · line-art trees", "용도별 색 구분 · color-coded program zones"]
SECTION_DEFAULT = ["절단 벽 검정 포셰 · solid black poché walls", "지반 해치 · ground hatch",
                   "옅은 하늘 그라데이션 · soft sky gradient", "실루엣 인물 · silhouette people",
                   "채광 광선 · daylight rays", "원경 건물 회색 · grey background buildings", "단면 투시 · section perspective"]

DEFAULT_KEYWORDS = ["액소노메트릭 · axonometric view", "미니멀 플랫 · minimal flat vector", "손그림 선 · hand-drawn line",
                    "수채화 워시 · watercolor wash", "용도별 색 구분 · color-coded program zones",
                    "동선 화살표 · circulation arrows", "톤다운 색감 · muted tones", "분해 액소 · exploded axonometric"]

# 아무 것도 안 맞을 때: 다이어그램 유형에 어울리는 건축 언어
TYPE_FALLBACK = {
    "매스 형성 과정": ["매스의 분절 · massing articulation", "볼륨의 변형 · volumetric transformation", "비워냄 · subtractive void"],
    "프로그램 조닝": ["켜별 조닝 · layered zoning", "공용·사적 위계 · public-private gradient", "볼륨별 프로그램 · program volumes"],
    "동선": ["산책로 · promenade", "시퀀스 · spatial sequence", "수직 동선 코어 · vertical circulation core"],
    "분해 액소": ["구축의 켜 · tectonic layers", "부재의 결합 · assembly of parts", "층별 분리 · floor-by-floor separation"],
    "환경 (빛·바람)": ["패시브 디자인 · passive design", "맞통풍 · cross ventilation", "빛의 우물 · light well"],
    "단면 다이어그램": ["단면의 깊이 · sectional depth", "보이드 · interlocking voids", "지형과 단면 · section with terrain"],
    "배치·맥락": ["도시 맥락 · urban context", "축과 관계 · site axes", "주변 볼륨 회색 처리 · context in grey"],
    "구조·재료": ["구조 리듬 · structural rhythm", "재료의 켜 · material layers", "접합 상세 · joint details"],
    "컨셉 다이어그램": ["개념적 추상화 · conceptual abstraction", "핵심 제스처 · single bold gesture", "은유적 형태 · metaphorical form"],
    "단계별 시퀀스": ["단계적 변화 · step-by-step sequence", "번호 매긴 과정 · numbered process", "전후 비교 · before → after"],
}
TYPE_FALLBACK.update({
    "실별 색 구분": ["공용·사적 위계 · public-private gradient", "켜 공간 · layered thresholds"],
    "그림자·깊이감": ["빛과 그림자 대비 · chiaroscuro", "깊은 처마 그림자 · deep eave shadow"],
    "절단면 포셰 강조": ["단면의 깊이 · sectional depth", "절단면 검정 포셰 · solid black poché"],
    "빛·환경 흐름": ["빛의 우물 · light well", "맞통풍 · cross ventilation"],
    "단면 투시(깊이감)": ["단면 투시 · section perspective", "보이드 · interlocking voids"],
})
DEFAULTS_BY_WORK = {}  # 아래에서 채움

GENERAL_ARCH = ["절제된 여백 · restrained void", "빛과 그림자 대비 · chiaroscuro", "켜 공간 · layered thresholds",
                "열린 평면 · open plan", "반복되는 리듬 · rhythmic repetition", "재료의 솔직함 · honest materiality"]

_SPLIT = re.compile(r"[,.\n;/·]+|\s(?:그리고|및|하고|이면서|면서)\s")


def split_phrases(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(text or "") if p and p.strip()]


_FALSE_FRIENDS = ["자연스럽", "자연스러"]  # '자연'이 들어있지만 자연(nature) 뜻이 아닌 표현


def _match(groups, phrase: str) -> list[str]:
    t = phrase.lower()
    for ff in _FALSE_FRIENDS:
        t = t.replace(ff, "")
    out: list[str] = []
    for triggers, kws in groups:
        if any(trig in t for trig in triggers):
            out += [k for k in kws if k not in out]
    return out


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _fuzzy(phrase: str) -> list[str]:
    """트리거나 키워드 한국어 이름과 글자 조각(2글자)이 겹치는 그룹 추천."""
    pb = _bigrams(phrase)
    scored = []
    for triggers, kws in GROUPS + ARCH_LANG:
        vocab = set().union(*(_bigrams(t) for t in triggers), *(_bigrams(ko(k)) for k in kws))
        score = len(pb & vocab)
        if score >= 2:  # 한 조각만 겹치면 우연일 가능성이 커서 제외
            scored.append((score, kws))
    out: list[str] = []
    for _, kws in sorted(scored, key=lambda x: -x[0])[:2]:
        out += [k for k in kws if k not in out]
    return out


def suggest_for_phrase(phrase: str, diagram_types: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(직접 대체 그래픽 키워드, 비슷한 느낌의 건축 언어) — 건축 언어는 항상 채워서 돌려준다."""
    direct = _match(GROUPS, phrase)[:8]
    similar = [k for k in _match(ARCH_LANG, phrase) if k not in direct]
    if not similar:
        similar = [k for k in _fuzzy(phrase) if k not in direct]
    if not similar:
        for t in diagram_types or []:
            similar += [k for k in TYPE_FALLBACK.get(t, []) if k not in similar]
    if not similar:
        similar = GENERAL_ARCH
    return direct, similar[:8]


def suggest_by_phrase(text: str, diagram_types: list[str] | None = None):
    """[(구절, 직접 대체, 비슷한 느낌의 건축 언어)]"""
    return [(p, *suggest_for_phrase(p, diagram_types)) for p in split_phrases(text)]


def ko(label: str) -> str:
    return label.split(" · ")[0]


DEFAULTS_BY_WORK.update({"다이어그램": DEFAULT_KEYWORDS, "평면 리터칭": PLAN_DEFAULT, "단면 리터칭": SECTION_DEFAULT})
