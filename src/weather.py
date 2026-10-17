"""날씨 조회 + 실내/실외 판정 규칙.

입력: 날짜·좌표·활동 시간대 → 출력: {temp, rain_prob, pm, wind, 판정, 근거, ...}

데이터 소스 우선순위 (키가 없어도 동작):
  1) data/weather_kma.json  — 기상청 단기예보를 웹검색으로 확인해 적어 둔 값 (Claude가 실행 시 채움)
  2) OpenWeatherMap         — .env 에 OPENWEATHER_API_KEY 가 있을 때만
  3) Open-Meteo             — 키 불필요 무료 API (기온·체감·강수·바람 + 미세먼지)
  4) 기본값                  — 모두 실패하면 '실외안 + 확인 필요' 로 진행 (멈추지 않음)
"""
import json
import os
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
KMA_FILE = ROOT / "data" / "weather_kma.json"
TIMEOUT = 15


# ───────────────────────── 판정 규칙 (기획안 2-4) ─────────────────────────
def pm_grade(pm10, pm25):
    """환경부 기준 미세먼지 등급. 둘 중 나쁜 쪽을 따른다."""
    def g10(v):
        return "좋음" if v <= 30 else "보통" if v <= 80 else "나쁨" if v <= 150 else "매우나쁨"

    def g25(v):
        return "좋음" if v <= 15 else "보통" if v <= 35 else "나쁨" if v <= 75 else "매우나쁨"

    order = ["좋음", "보통", "나쁨", "매우나쁨"]
    grades = [g10(pm10) if pm10 is not None else None, g25(pm25) if pm25 is not None else None]
    grades = [x for x in grades if x]
    return max(grades, key=order.index) if grades else None


def judge(w):
    """w: {rain_prob, rain_mm, feels_min, feels_max, pm_grade, wind} → (판정, 근거목록, 플랜B문구)"""
    reasons, plan_b = [], None
    rp, mm = w.get("rain_prob"), w.get("rain_mm")
    if (rp is not None and rp >= 60) or (mm is not None and mm >= 1):
        reasons.append(f"강수확률 {rp}%·시간당 최대 {mm}mm (기준 ≥60% 또는 ≥1mm/h)")
    if w.get("feels_min") is not None and w["feels_min"] <= 0:
        reasons.append(f"체감 최저 {w['feels_min']}℃ (기준 ≤0℃)")
    if w.get("feels_max") is not None and w["feels_max"] >= 31:
        reasons.append(f"체감 최고 {w['feels_max']}℃ (기준 ≥31℃)")
    if w.get("pm_grade") in ("나쁨", "매우나쁨"):
        reasons.append(f"미세먼지 {w['pm_grade']}")
    if w.get("wind") is not None and w["wind"] >= 9:
        reasons.append(f"풍속 {w['wind']}m/s (기준 ≥9m/s)")

    if reasons:
        return "실내", reasons, None
    if rp is not None and 40 <= rp < 60:
        plan_b = f"강수확률 {rp}% — 출발 전 비 소식이 있으면 실내안으로 전환하세요 (플랜 B 전환 포인트)"
    return "실외", ["강수·기온·미세먼지·바람 모두 기준 이내"], plan_b


def icon(w):
    if w.get("rain_prob") is not None and w["rain_prob"] >= 60:
        return "🌧"
    if w.get("rain_prob") is not None and w["rain_prob"] >= 30:
        return "☁️"
    return "☀️"


# ───────────────────────── 데이터 소스 ─────────────────────────
def _from_kma_file(d):
    if not KMA_FILE.exists():
        return None
    data = json.loads(KMA_FILE.read_text(encoding="utf-8"))
    row = data.get(d.isoformat())
    if not row:
        return None
    row = dict(row)
    row.setdefault("pm_grade", None)
    row["source"] = f"기상청 단기예보(웹검색, {data.get('_조회시각', '시각 미기록')})"
    return row


def _from_openweather(d, lat, lng, hours):
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not key:
        return None
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={"lat": lat, "lon": lng, "appid": key, "units": "metric", "lang": "kr"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    rows = [x for x in r.json()["list"] if x["dt_txt"].startswith(d.isoformat())
            and hours[0] <= int(x["dt_txt"][11:13]) <= hours[1]]
    if not rows:
        return None
    return {
        "temp": round(max(x["main"]["temp"] for x in rows), 1),
        "feels_min": round(min(x["main"]["feels_like"] for x in rows), 1),
        "feels_max": round(max(x["main"]["feels_like"] for x in rows), 1),
        "rain_prob": round(max(x.get("pop", 0) for x in rows) * 100),
        "rain_mm": round(max(x.get("rain", {}).get("3h", 0) / 3 for x in rows), 1),
        "wind": round(max(x["wind"]["speed"] for x in rows), 1),
        "pm_grade": None,
        "source": "OpenWeatherMap",
    }


def _from_open_meteo(d, lat, lng, hours):
    common = {"latitude": lat, "longitude": lng, "timezone": "Asia/Seoul",
              "start_date": d.isoformat(), "end_date": d.isoformat()}
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={**common, "wind_speed_unit": "ms",
                "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    idx = [i for i, t in enumerate(h["time"]) if hours[0] <= int(t[11:13]) <= hours[1]]
    pick = lambda k: [h[k][i] for i in idx if h[k][i] is not None]
    w = {
        "temp": round(max(pick("temperature_2m")), 1),
        "feels_min": round(min(pick("apparent_temperature")), 1),
        "feels_max": round(max(pick("apparent_temperature")), 1),
        "rain_prob": max(pick("precipitation_probability") or [0]),
        "rain_mm": round(max(pick("precipitation") or [0]), 1),
        "wind": round(max(pick("wind_speed_10m")), 1),
        "pm_grade": None,
        "source": "Open-Meteo (키 불필요)",
    }
    try:
        a = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality",
                         params={**common, "hourly": "pm10,pm2_5"}, timeout=TIMEOUT)
        a.raise_for_status()
        ah = a.json()["hourly"]
        pm10 = [ah["pm10"][i] for i in idx if ah["pm10"][i] is not None]
        pm25 = [ah["pm2_5"][i] for i in idx if ah["pm2_5"][i] is not None]
        w["pm10"] = round(max(pm10)) if pm10 else None
        w["pm25"] = round(max(pm25)) if pm25 else None
        w["pm_grade"] = pm_grade(w["pm10"], w["pm25"])
    except Exception:
        pass
    return w


def get_weather(d: date, lat: float, lng: float, hours=(9, 17)):
    """활동 시간대(hours) 기준 날씨 + 판정. 실패해도 예외를 던지지 않는다."""
    errors = []
    w = None
    for fn in (lambda: _from_kma_file(d),
               lambda: _from_openweather(d, lat, lng, hours),
               lambda: _from_open_meteo(d, lat, lng, hours)):
        try:
            w = fn()
            if w:
                break
        except Exception as e:  # 다음 소스로 넘어간다
            errors.append(str(e)[:80])

    if not w:
        return {"date": d.isoformat(), "판정": "실외", "icon": "❔", "확인필요": True,
                "근거": ["날씨 조회 실패 — 기본값 '실외안 + 확인 필요'로 진행"] + errors,
                "plan_b": "출발 전 기상청 날씨누리에서 꼭 확인하세요", "source": "기본값"}

    verdict, reasons, plan_b = judge(w)
    return {"date": d.isoformat(), **w, "판정": verdict, "근거": reasons,
            "plan_b": plan_b, "icon": icon(w), "확인필요": False}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(json.dumps(get_weather(d, 37.514, 126.856), ensure_ascii=False, indent=2))
