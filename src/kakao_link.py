"""카카오맵 링크 생성 규칙 (API 키 불필요).

우선순위: 장소 ID > 좌표(길찾기) > 검색(지역명+장소명)
"""
from urllib.parse import quote


def kakao_link(place):
    """place: {name, area?, lat?, lng?, kakao_id?} → (url, 종류)"""
    if place.get("kakao_id"):
        return f"https://place.map.kakao.com/{place['kakao_id']}", "장소상세"
    if place.get("lat") is not None and place.get("lng") is not None:
        return f"https://map.kakao.com/link/to/{quote(place['name'])},{place['lat']},{place['lng']}", "길찾기"
    query = f"{place.get('area', '')} {place['name']}".strip()
    return f"https://map.kakao.com/link/search/{quote(query)}", "검색"


if __name__ == "__main__":
    for p in ({"name": "국립항공박물관", "kakao_id": "12345"},
              {"name": "서울식물원", "lat": 37.5694, "lng": 126.835},
              {"name": "레이크우드", "area": "시흥"}):
        print(kakao_link(p))
