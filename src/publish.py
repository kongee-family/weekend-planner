"""퍼블리셔 — 대시보드 HTML 생성 + 슬랙 전송.

입력: 확정 계획(plan) → 출력: output/dashboard.html + 슬랙 메시지 1통
"""
import os
import time
import webbrowser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import cost
import places
from kakao_link import kakao_link

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "output" / "dashboard.html"


# ───────────────────────── 대시보드 ─────────────────────────
TEMPLATES = {"classic": "dashboard.html.j2", "pixel": "dashboard_pixel.html.j2"}


def render_dashboard(plan, open_browser=True, style="classic", out=DASHBOARD):
    """style: 'classic'(방안1) | 'pixel'(방안2, 픽셀 스타일)"""
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=True)
    place_list = []
    for p in places.load_places():
        place_list.append({**p, "kakao_url": kakao_link(p)[0], "price": p.get("price", {})})
    html = env.get_template(TEMPLATES[style]).render(plan=plan, items=cost.ITEMS, place_list=place_list)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.as_uri())
    return out


def dashboard_ref():
    """슬랙에 넣을 대시보드 주소: 웹 주소(DASHBOARD_URL, GitHub Pages)가 있으면 그것, 없으면 로컬 파일 경로."""
    return os.getenv("DASHBOARD_URL") or str(DASHBOARD)


# ───────────────────────── 슬랙 (기획안 10-2 형식) ─────────────────────────
def slack_text(plan, dashboard_ref):
    lines = [f"⭐ 이번 주말 확정안 ({plan['range']})", ""]
    for d in plan["days"]:
        w, o = d["weather"], d["options"][d["selected"]]
        if w.get("확인필요"):
            wx = "날씨 확인 필요"
        else:
            wx = f"{w['temp']}℃·강수 {w['rain_prob']}%"
            if w.get("pm_grade") in ("나쁨", "매우나쁨"):
                wx += f"·미세먼지 {w['pm_grade']}"
        lines.append(f"🌤 {d['day']} {d['label']} {w['icon']} {wx} → {d['selected']}안")
        for r in o["timeline"]:
            s = r["stop"]
            if s:
                badges = " ".join(s["badges"])
                lines.append(f" {r['time']} {s['name']} {badges} 🗺 <{s['kakao_url']}|카카오맵>".replace("  ", " "))
            else:
                lines.append(f" {r['time']} {r['label']}")
        if w.get("plan_b"):
            lines.append(f" 🔀 {w['plan_b']}")
        if o.get("reservation"):
            lines.append(" 📌 예약 필요 — 방문 전 공식 홈페이지 확인")
        lines.append(f" 💰 {d['day']} 예상 {o['cost']['합계']:,}원")
        lines.append("")
    lines.append(f"💰 주말 합계 약 {plan['weekend_total']['합계']:,}원 (예상)")
    lines.append(f"📊 상세: {dashboard_ref}")
    v = plan.get("verify")
    if v and not v["pass"]:
        lines.append("❗ 점검 필요: " + " / ".join(v["issues"]))
    if not plan.get("web_info_ok", True):
        lines.append("⚠️ 웹 정보 미확보 — 검증 리스트만으로 구성")
    return "\n".join(lines)


def send_slack(text):
    """전송 실패 시 사유를 터미널에 출력하고 1회 재시도. 성공 여부를 돌려준다."""
    token, channel = os.getenv("SLACK_BOT_TOKEN"), os.getenv("SLACK_CHANNEL")
    if not token or not channel:
        print("❌ 슬랙 전송 불가: .env 에 SLACK_BOT_TOKEN / SLACK_CHANNEL 이 비어 있어요.")
        return False
    client = WebClient(token=token)
    for attempt in (1, 2):
        try:
            client.chat_postMessage(channel=channel, text=text, unfurl_links=False, unfurl_media=False)
            print(f"✅ 슬랙 전송 완료 (채널 {channel})")
            return True
        except SlackApiError as e:
            print(f"❌ 슬랙 전송 실패 ({attempt}/2): {e.response.get('error')}")
        except Exception as e:
            print(f"❌ 슬랙 전송 실패 ({attempt}/2): {e}")
        if attempt == 1:
            time.sleep(3)
            print("↻ 3초 후 재시도합니다…")
    return False
