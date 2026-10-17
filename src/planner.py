"""주말 나들이 플래너 — 전체 흐름 실행 (여기를 실행하면 끝).

실행: .venv/bin/python src/planner.py
흐름: 날짜 → ①날씨 판정 → ②장소·식당·카페 매칭 → ③비용 → (④검증 → ⑤대시보드·슬랙)
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

import cost
import places
import publish
import weather
from kakao_link import kakao_link
from verify import verify

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
WEEKDAYS = "월화수목금토일"
ACTIVITY_HOURS = {"토": (9, 17), "일": (9, 13)}
DEFAULT_HOP_KM = 10  # 좌표 없는 식당·카페까지 추정 거리


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def this_weekend(today=None):
    """이번 주 토·일 날짜. 오늘이 일요일이면 어제(토)와 오늘(일)."""
    today = today or date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    if today.weekday() == 6:
        sat = today - timedelta(days=1)
    return sat, sat + timedelta(days=1)


def fmt(d):
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def hm(t):
    return t.strftime("%H:%M")


def stop(kind, p, extra=""):
    """시간표 한 줄에 들어갈 장소 정보 + 카카오맵 링크"""
    if not p:
        return None
    url, link_type = kakao_link(p)
    badges = []
    if p["category"] == "식당":
        badges += [f"{p['baby_chair']}아기의자", f"{p['low_salt']}저염"]
    if p["category"] == "카페":
        badges += [f"{p['baby_chair']}아기의자", f"{p['spacious']}넓음"]
    return {"kind": kind, "id": p["id"], "name": p["name"], "category": p["category"], "area": p["area"],
            "indoor": p["indoor"], "검증": p["검증"], "badges": badges, "note": extra,
            "kakao_url": url, "link_type": link_type}


def build_course(day, d, verdict, cfg, recent):
    """요일 템플릿(기획안 2-2)에 장소를 끼워 넣어 시간표를 만든다. 후보가 없으면 None."""
    cands = places.candidates(day, verdict, d, recent)
    if not cands:
        return None
    main = cands[0]
    lunch = places.match(main, "식당")
    cafe = places.match(main, "카페") if day == "토" else None
    drive = main["drive"]["min"]
    at = lambda s: datetime.combine(d, datetime.strptime(s, "%H:%M").time())

    rows = []
    if day == "토":
        start = at(cfg["saturday"]["depart"])
        arrive = start + timedelta(minutes=drive)
        rows.append({"time": hm(start), "label": f"출발 (집 → {main['area']} 약 {drive}분)", "stop": None})
        rows.append({"time": hm(arrive), "label": "오전 메인 활동", "stop": stop("활동", main, main["price"]["note"])})
        rows.append({"time": "11:30", "label": "점심", "stop": stop("점심", lunch, lunch.get("menu_hint", "") if lunch else "")})
        rows.append({"time": "12:30", "label": "이동 + 차 낮잠 (카시트 낮잠 길이에 맞춰 드라이브 조절)", "stop": None})
        rows.append({"time": "14:30", "label": "오후 카페 (마당·넓은 공간)", "stop": stop("카페", cafe)})
        rows.append({"time": "16:00", "label": f"귀가 (정체 고려) → {cfg['saturday']['return']} 도착 목표", "stop": None})
        stay_min = int((at("11:30") - arrive).total_seconds() // 60) + 60  # 점심까지 같은 주차장 가정
        hops = 2
    else:
        start = at(cfg["sunday"]["depart"])
        arrive = start + timedelta(minutes=drive)
        rows.append({"time": hm(start), "label": f"출발 (집 → {main['area']} 약 {drive}분)", "stop": None})
        rows.append({"time": hm(arrive), "label": "활동", "stop": stop("활동", main, main["price"]["note"])})
        rows.append({"time": "11:30", "label": "점심", "stop": stop("점심", lunch, lunch.get("menu_hint", "") if lunch else "")})
        rows.append({"time": "12:30", "label": f"귀가 → {cfg['sunday']['return']} 집 도착, 낮잠", "stop": None})
        stay_min = int((at("11:30") - arrive).total_seconds() // 60) + 60
        hops = 1

    course = {"verdict": verdict, "main": main, "lunch": lunch, "cafe": cafe,
              "stay_min": stay_min, "total_km": main["drive"]["km"] * 2 + DEFAULT_HOP_KM * hops}
    return {"verdict": verdict, "timeline": rows, "alternatives": [c["name"] for c in cands[1:3]],
            "reservation": main.get("reservation", False),
            "cost": cost.course_cost(course, cfg), "total_km": course["total_km"]}


def build_plan(today=None):
    load_dotenv(ROOT / ".env")
    cfg = load_config()
    origin = cfg["origin"]
    recent = {v["id"] for v in cfg.get("recent_visits", [])}
    sat, sun = this_weekend(today)
    web_ok = bool(places.load_places())

    days = []
    for day, d in (("토", sat), ("일", sun)):
        w = weather.get_weather(d, origin["lat"], origin["lng"], ACTIVITY_HOURS[day])
        options = {v: build_course(day, d, v, cfg, recent) for v in ("실외", "실내")}
        selected = w["판정"] if options.get(w["판정"]) else next(v for v, o in options.items() if o)
        days.append({"day": day, "date": d.isoformat(), "label": fmt(d), "weather": w,
                     "selected": selected, "options": options})

    return {"generated_at": datetime.now().isoformat(timespec="minutes"),
            "origin": origin["name"], "range": f"{sat.month}/{sat.day}~{sun.day}",
            "web_info_ok": web_ok, "days": days,
            "weekend_total": cost.weekend_total([x["options"][x["selected"]]["cost"] for x in days])}


def print_plan(plan):
    print(f"🚗 주말 나들이 플래너 — 출발지: {plan['origin']}  ({plan['range']})\n")
    for x in plan["days"]:
        w, opt = x["weather"], x["options"][x["selected"]]
        print(f"{w['icon']} {x['day']} {x['label']} → {x['selected']}안   ({' / '.join(w['근거'])})")
        for r in opt["timeline"]:
            s = r["stop"]
            line = f"   {r['time']}  {r['label']}"
            if s:
                line += f" · {s['name']} {s['검증']} {' '.join(s['badges'])}\n          🗺 {s['kakao_url']}"
            print(line)
        c = opt["cost"]
        print("   💰 " + " · ".join(f"{k} {c[k]['amount']:,}" for k in cost.ITEMS) + f"  = 예상 {c['합계']:,}원\n")
    print(f"💰 주말 합계 예상 {plan['weekend_total']['합계']:,}원")


def main():
    no_slack = "--no-slack" in sys.argv
    if "--send-only" in sys.argv:  # 자동 실행: 대시보드 게시 후 저장된 계획으로 슬랙만 전송
        load_dotenv(ROOT / ".env")
        plan = json.loads((OUTPUT / "plan.json").read_text(encoding="utf-8"))
        ok = publish.send_slack(publish.slack_text(plan, publish.dashboard_ref()))
        sys.exit(0 if ok else 1)

    plan = build_plan()
    recent = {v["id"] for v in load_config().get("recent_visits", [])}
    plan["verify"] = verify(plan, recent)
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print_plan(plan)
    print(f"\n📝 저장: {OUTPUT / 'plan.json'}")

    v = plan["verify"]
    print(f"\n🔎 검증: {'통과' if v['pass'] else '수정 필요'} (참고 {len(v['notes'])}건)")
    for msg in v["issues"]:
        print(f"   ❗ {msg}")

    path = publish.render_dashboard(plan, open_browser="--no-open" not in sys.argv,
                                    style=load_config().get("dashboard_style", "classic"))
    print(f"📊 대시보드: {path}")
    if not no_slack:
        publish.send_slack(publish.slack_text(plan, publish.dashboard_ref()))


if __name__ == "__main__":
    main()
