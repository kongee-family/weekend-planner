"""비용 계산 — 입장료·식비·카페·주차·유류비·통행료. 모두 '예상' 값이며 산출 근거를 함께 돌려준다.

입력: 코스(main 장소, 식당, 카페, 체류시간, 이동거리) + 설정 → 출력: {항목: {amount, 근거}, 합계}
"""
import math

ITEMS = ["입장료", "식비", "카페", "주차", "유류비", "통행료"]


def won(n):
    return f"{int(round(n)):,}원"


def parking_fee(rule, stay_min):
    """places.json 의 parking 규칙 → (요금, 근거)"""
    kind = rule.get("rule", "free")
    if not rule.get("available", True):
        return 0, "주차 불가"
    if kind == "free":
        return 0, f"무료 ({rule.get('note', '')})"
    if kind == "flat":
        return rule["fee"], f"1일 정액 {won(rule['fee'])}"
    # 시간제: 기본(무료/최초) 구간 이후 10분 또는 15분 단위 가산
    free_min = rule.get("free_min", 0)
    if stay_min <= free_min:
        return 0, f"{free_min}분 이내 무료"
    step, unit = (10, rule["per10"]) if "per10" in rule else (15, rule.get("per15", 0))
    # 최초요금(first)이 덮는 시간: first_min 이 있으면 그 값, 없으면 무료시간 + 한 단위
    base_min = rule.get("first_min", free_min + step if rule.get("first") else free_min)
    extra_steps = math.ceil(max(0, stay_min - base_min) / step)
    fee = rule.get("first", 0) + extra_steps * unit
    return fee, f"{rule.get('note', '시간제')} × 체류 {stay_min}분"


def course_cost(course, cfg):
    adults = cfg["family"]["adults"]
    car = cfg["car"]
    main, food, cafe = course["main"], course.get("lunch"), course.get("cafe")
    out = {}

    pr = main.get("price", {})
    out["입장료"] = {"amount": adults * pr.get("adult", 0) + pr.get("baby", 0),
                   "근거": f"성인 {adults} × {won(pr.get('adult', 0))} + 24개월 {won(pr.get('baby', 0))} — {pr.get('note', '')}"}

    if food:
        fp = food["price"]
        out["식비"] = {"amount": adults * fp["adult_avg"] + fp["baby_menu"],
                     "근거": f"성인 {adults} × 평균 {won(fp['adult_avg'])} + 아기메뉴/공기밥 {won(fp['baby_menu'])}"}
    else:
        out["식비"] = {"amount": 0, "근거": "식당 미정"}

    if cafe:
        cp = cafe["price"]
        out["카페"] = {"amount": 2 * cp["drink_avg"] + cp["snack"],
                     "근거": f"음료 2 × {won(cp['drink_avg'])} + 아기 간식 {won(cp['snack'])}"}
    else:
        out["카페"] = {"amount": 0, "근거": "카페 일정 없음"}

    fee, why = parking_fee(main.get("parking", {}), course["stay_min"])
    out["주차"] = {"amount": fee, "근거": f"{main['name']}: {why}"}

    km = course["total_km"]
    liters = km / car["fuel_efficiency_km_per_l"]
    out["유류비"] = {"amount": int(round(liters * car["fuel_price_won_per_l"], -2)),
                   "근거": f"왕복 약 {km}km ÷ {car['fuel_efficiency_km_per_l']}km/L × {won(car['fuel_price_won_per_l'])}/L ({car['fuel_type']})"}

    toll = main.get("drive", {}).get("toll", 0) * 2
    out["통행료"] = {"amount": toll, "근거": "무료도로 경로 기준" if toll == 0 else f"왕복 {won(toll)}"}

    out["합계"] = sum(out[k]["amount"] for k in ITEMS)
    return out


def weekend_total(costs):
    """costs: [토 비용, 일 비용] → 항목별 합 + 총액"""
    total = {k: sum(c[k]["amount"] for c in costs) for k in ITEMS}
    total["합계"] = sum(total.values())
    return total
