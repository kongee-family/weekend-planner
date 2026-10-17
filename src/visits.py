"""방문 기록(히스토리) — 다녀온 장소를 data/visits.json 에 남기고, 최근 4주 방문지를 추천에서 뺀다.

기록 방법
  1) 확정안 그대로 다녀왔을 때: 보관된 지난 계획(data/plans/토요일날짜.json)에서 장소를 꺼내 기록
  2) 계획에 없던 곳: 장소 이름(쉼표 구분) + 날짜로 기록

실행 예
  python src/visits.py record --days "토·일 모두" --rating 5 --memo "기차 엄청 좋아함"
  python src/visits.py record --names "서울식물원, 호호방 마곡" --date 2026-10-25
  python src/visits.py list
GitHub Actions 의 '방문 기록 남기기' 워크플로는 같은 값을 환경변수(V_DAYS 등)로 넘긴다.
"""
import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

import places

ROOT = Path(__file__).resolve().parent.parent
VISITS = ROOT / "data" / "visits.json"
PLANS = ROOT / "data" / "plans"
EXCLUDE_WEEKS = 4
DAY_CHOICES = {"토·일 모두": ("토", "일"), "토요일만": ("토",), "일요일만": ("일",)}


def load():
    try:
        return json.loads(VISITS.read_text(encoding="utf-8"))["visits"]
    except Exception:
        return []


def save(rows):
    rows = sorted(rows, key=lambda v: (v["date"], v["name"]))
    VISITS.write_text(json.dumps({
        "_안내": "다녀온 장소 기록. revisit=true(또 가고 싶어요)이면 4주 제외 없이 다시 추천돼요.",
        "visits": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def excluded_until(v):
    """이 방문 때문에 추천에서 빠지는 마지막 날짜 (revisit 이면 None)"""
    if v.get("revisit"):
        return None
    return date.fromisoformat(v["date"]) + timedelta(weeks=EXCLUDE_WEEKS)


def recent_ids(ref):
    """ref(이번 토요일) 기준 최근 4주 안에 다녀온 장소 id 집합. '또 가고 싶어요'는 제외하지 않음."""
    out = set()
    for v in load():
        until = excluded_until(v)
        if v.get("id") and until and date.fromisoformat(v["date"]) <= ref <= until:
            out.add(v["id"])
    return out


def history(ref, limit=20):
    """대시보드용: 최근 기록부터, 제외 여부 표시 포함"""
    rows = []
    for v in sorted(load(), key=lambda v: v["date"], reverse=True)[:limit]:
        until = excluded_until(v)
        rows.append({**v, "excluded": bool(until and date.fromisoformat(v["date"]) <= ref <= until),
                     "until": until.isoformat() if until else None})
    return rows


def latest_past_plan(today):
    """보관된 계획 중 토요일이 오늘 이전(=이미 지난 주말)인 가장 최근 것"""
    files = sorted(p for p in PLANS.glob("*.json") if date.fromisoformat(p.stem) <= today)
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def _row(d, stop_id, name, category, rating, memo, revisit):
    return {"date": d, "id": stop_id, "name": name, "category": category,
            "rating": rating, "memo": memo, "revisit": revisit}


def record(days="토·일 모두", rating=None, memo="", revisit=False, names="", visit_date="", today=None):
    today = today or date.today()
    rows, added = load(), []
    seen = {(v["date"], v["name"]) for v in rows}

    if names.strip():  # 계획에 없던 곳
        d = visit_date.strip() or (today - timedelta(days=(today.weekday() - 5) % 7)).isoformat()
        by_name = places.load_places()
        for n in (x.strip() for x in names.split(",") if x.strip()):
            hit = next((p for p in by_name if n in p["name"] or p["name"] in n), None)
            added.append(_row(d, hit["id"] if hit else None, hit["name"] if hit else n,
                              hit["category"] if hit else "기타", rating, memo, revisit))
    else:  # 지난 확정안 그대로
        plan = latest_past_plan(today)
        if not plan:
            raise SystemExit("❌ 보관된 지난 계획이 없어요. 장소 이름(names)과 날짜(date)를 직접 입력해 주세요.")
        for d in plan["days"]:
            if d["day"] not in DAY_CHOICES.get(days, ("토", "일")):
                continue
            for r in d["options"][d["selected"]]["timeline"]:
                s = r["stop"]
                if s:
                    added.append(_row(d["date"], s["id"], s["name"], s["category"], rating, memo, revisit))

    added = [v for v in added if (v["date"], v["name"]) not in seen]
    save(rows + added)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "list"])
    ap.add_argument("--days", default=os.getenv("V_DAYS", "토·일 모두"))
    ap.add_argument("--rating", default=os.getenv("V_RATING", ""))
    ap.add_argument("--memo", default=os.getenv("V_MEMO", ""))
    ap.add_argument("--names", default=os.getenv("V_NAMES", ""))
    ap.add_argument("--date", default=os.getenv("V_DATE", ""))
    ap.add_argument("--revisit", action="store_true", default=os.getenv("V_REVISIT", "false") == "true")
    a = ap.parse_args()

    if a.cmd == "list":
        for v in history(date.today(), limit=100):
            flag = f"~{v['until']} 추천 제외" if v["excluded"] else ("또 가고 싶어요" if v.get("revisit") else "")
            print(f"{v['date']}  {v['name']}  {'⭐' * (v['rating'] or 0)}  {v['memo'] or ''}  {flag}")
        return

    rating = int(a.rating) if a.rating.isdigit() else None
    added = record(a.days, rating, a.memo.strip(), a.revisit, a.names, a.date)
    print(f"📝 방문 기록 {len(added)}건 추가")
    for v in added:
        print(f"   {v['date']} {v['name']} ({v['category']})")


if __name__ == "__main__":
    main()
