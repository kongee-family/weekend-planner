"""장소·식당·카페 매칭 (검증 리스트 우선, 부족분은 웹검색 보조).

입력: 요일·계절·실내외 → 출력: [{name, category, lat, lng, indoor, 검증, score, ...}]
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES_FILE = ROOT / "data" / "places.json"

TODDLER_FAVORITES = {"탈것", "동물", "물모래", "잔디", "키즈체험", "어린이박물관", "도서관유아실"}
SEASON_TAGS = {"가을": {"억새", "단풍", "농장"}, "겨울": {"눈썰매"}, "봄": {"꽃"}, "여름": {"물놀이"}}


def season_of(d):
    return {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
            6: "여름", 7: "여름", 8: "여름"}.get(d.month, "가을")


def load_places():
    """places.json 로드. 웹 정보가 없으면 빈 리스트 대신 예외 없이 [] 를 준다."""
    try:
        return json.loads(PLACES_FILE.read_text(encoding="utf-8"))["places"]
    except Exception:
        return []


def _fits_weather(place, verdict):
    if verdict == "실내":
        return place["indoor"] in ("실내", "혼합")
    return place["indoor"] in ("실외", "혼합")


def score(place, season):
    s = 0
    if place.get("sub") in TODDLER_FAVORITES:
        s += 2
    if season in place.get("season", []):
        s += 2
    elif "사계절" in place.get("season", []):
        s += 1
    if set(place.get("tags", [])) & SEASON_TAGS.get(season, set()):
        s += 1
    if place.get("검증") == "✅":
        s += 1
    return s


def candidates(day, verdict, d, recent_ids=()):
    """day: '토'|'일', verdict: '실내'|'실외'. 최근 4주 방문(recent_ids)과 ❌ 는 제외.
    같은 지역에 식당(+2)·카페(+1, 토요일만)가 있으면 가산 — 동선이 흩어지지 않게."""
    season = season_of(d)
    all_places = load_places()
    food_areas = {p["area"] for p in all_places if p["category"] == "식당" and p.get("검증") != "❌"}
    cafe_areas = {p["area"] for p in all_places if p["category"] == "카페" and not p.get("nokids")}
    rows = []
    for p in all_places:
        if p["category"] != "장소" or day not in p.get("day_fit", []):
            continue
        if p.get("검증") == "❌" or p["id"] in recent_ids:
            continue
        if not _fits_weather(p, verdict):
            continue
        exact = 2 if p["indoor"] == verdict else 0  # 완전 실내/실외가 혼합보다 우선
        pair = (2 if p["area"] in food_areas else 0) + (1 if day == "토" and p["area"] in cafe_areas else 0)
        rows.append({**p, "score": score(p, season) + exact + pair})
    return sorted(rows, key=lambda p: (-p["score"], p["drive"]["min"]))


def _dist_km(a, b):
    if None in (a.get("lat"), b.get("lat")):
        return 999
    dx = (a["lng"] - b["lng"]) * 88.0
    dy = (a["lat"] - b["lat"]) * 111.0
    return math.hypot(dx, dy)


def match(place, category, exclude=()):
    """장소 근처 식당/카페. 같은 지역 → 가까운 좌표 → ✅ 우선. 노키즈존·❌ 제외."""
    pool = [p for p in load_places()
            if p["category"] == category and p.get("검증") != "❌"
            and not p.get("nokids") and p["id"] not in exclude]
    if not pool:
        return None
    same_area = lambda p: 0 if p["area"] == place["area"] else 1
    verified = lambda p: 0 if p.get("검증") == "✅" else 1
    return sorted(pool, key=lambda p: (same_area(p), _dist_km(p, place), verified(p)))[0]


if __name__ == "__main__":
    from datetime import date
    for day in ("토", "일"):
        for v in ("실외", "실내"):
            names = [f"{p['name']}({p['score']})" for p in candidates(day, v, date.today())]
            print(day, v, names)
