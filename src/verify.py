"""최종 점검 — 링크·중복·노키즈존·최근 방문·❌ 장소.

입력: 완성 계획(plan) → 출력: {"pass": bool, "issues": [수정 필요], "notes": [참고]}
"""
import re

import places

KAKAO_URL = re.compile(r"^https://(place\.map\.kakao\.com/\d+|map\.kakao\.com/link/(to|search|map)/.+)$")


def verify(plan, recent_ids=()):
    by_id = {p["id"]: p for p in places.load_places()}
    issues, notes = [], []
    used_main = {}

    for d in plan["days"]:
        o = d["options"].get(d["selected"])
        if not o:
            issues.append(f"{d['label']}: 선택된 {d['selected']}안 코스가 비어 있음")
            continue
        stops = [r["stop"] for r in o["timeline"] if r["stop"]]

        ids = [s["id"] for s in stops]
        if len(ids) != len(set(ids)):
            issues.append(f"{d['label']}: 같은 장소가 하루에 두 번 들어감")

        for s in stops:
            p = by_id.get(s["id"], {})
            if not KAKAO_URL.match(s["kakao_url"]):
                issues.append(f"{s['name']}: 카카오맵 링크 형식 오류 ({s['kakao_url']})")
            if p.get("nokids"):
                issues.append(f"{s['name']}: 노키즈존")
            if p.get("검증") == "❌":
                issues.append(f"{s['name']}: ❌ 표시된 장소")
            if s["id"] in recent_ids:
                issues.append(f"{s['name']}: 최근 4주 내 방문한 장소")
            if s["link_type"] == "검색":
                notes.append(f"{s['name']}: 좌표·ID 없음 → 검색 링크 (동명 장소 주의)")
            if s["검증"] == "⚠️":
                notes.append(f"{s['name']}: ⚠️ 방문 전 전화 확인 권장")

        main = next((s for s in stops if s["kind"] == "활동"), None)
        if main:
            if main["id"] in used_main:
                issues.append(f"{main['name']}: 토·일 중복 ({used_main[main['id']]}와 겹침)")
            used_main[main["id"]] = d["label"]
        if o.get("reservation"):
            notes.append(f"{d['label']} {main['name'] if main else ''}: 예약 필요")
        if d["weather"].get("확인필요"):
            notes.append(f"{d['label']}: 날씨 조회 실패 — 출발 전 확인")

    return {"pass": not issues, "issues": issues, "notes": list(dict.fromkeys(notes))}
