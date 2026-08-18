"""자료/*.xlsx -> data/funerals.json, data/areas.json

실행: python tools/generator/build_data.py
- idempotent (재실행해도 같은 결과)
- 랜덤 시드 없음. 변형 배정은 hash(장례식장명) 기반 결정론적.
- 주소/시도 파싱 실패 행은 _errors.csv 로 빼고 원본에 없는 값을 추정하지 않는다.
"""
import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
import yaml

ROOT = __file__.replace("\\", "/").rsplit("/tools/", 1)[0]
XLSX_PATH = f"{ROOT}/자료/전국 장례식장 리스트 1000+ 간단정리.xlsx"
CONFIG_PATH = f"{ROOT}/config/site.yaml"
OUT_FUNERALS = f"{ROOT}/data/funerals.json"
OUT_AREAS = f"{ROOT}/data/areas.json"
OUT_ERRORS = f"{ROOT}/tools/generator/_errors.csv"
OUT_REPORT = f"{ROOT}/tools/generator/_report.txt"

PER_DAY = 30
BASE_HOUR = 9
INTERVAL_MIN = 24
VARIANT_SECTIONS = ["intro", "delivery", "order", "faq", "outro"]
VARIANT_COUNT = 5

SIDO_MAP = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}

FACILITY_MAP = {
    "장애인 편의시설": "장애인 편의시설", "장애인편의시설": "장애인 편의시설", "장애인 시설": "장애인 편의시설",
    "주차장": "주차장", "주차": "주차장", "주차시설": "주차장",
}


def clean_name(raw: str) -> str:
    s = unicodedata.normalize("NFC", str(raw).strip())
    return re.sub(r"\s+", " ", s)


def clean_phone(raw) -> tuple[str | None, str | None]:
    if pd.isna(raw) or not str(raw).strip():
        return None, "빈 전화번호"
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None, f"숫자 없음: {raw}"
    if digits.startswith("02"):
        area, rest = digits[:2], digits[2:]
    else:
        area, rest = digits[:3], digits[3:]
    if area in ("010", "011", "016", "017", "018", "019"):
        return None, f"지역번호 없음(휴대폰 형식): {raw}"
    if len(rest) == 7:
        mid, last = rest[:3], rest[3:]
    elif len(rest) == 8:
        mid, last = rest[:4], rest[4:]
    else:
        return None, f"자릿수 이상: {raw}"
    return f"{area}-{mid}-{last}", None


def parse_address(raw: str) -> tuple[dict | None, str | None]:
    s = unicodedata.normalize("NFC", str(raw).strip())
    m = re.search(r"\(([^()]*)\)\s*$", s)
    if m:
        addr_detail = m.group(1).strip()
        remaining = s[: m.start()].strip()
    else:
        addr_detail = ""
        remaining = s
    tokens = remaining.split()
    if len(tokens) < 2:
        return None, f"주소 토큰 부족: {raw}"
    sido_full = tokens[0]
    sido = SIDO_MAP.get(sido_full)
    if sido is None:
        return None, f"알 수 없는 시도: {sido_full} ({raw})"

    if sido == "세종":
        sigungu = "세종시"
        road = " ".join(tokens[1:])
    else:
        unit1 = tokens[1]
        if unit1[-1] not in ("시", "군", "구"):
            return None, f"시군구 형식 아님: {unit1} ({raw})"
        if unit1.endswith("시") and len(tokens) > 2 and tokens[2][-1] in ("구", "군"):
            sigungu = f"{unit1} {tokens[2]}"
            road = " ".join(tokens[3:])
        else:
            sigungu = unit1
            road = " ".join(tokens[2:])

    return {
        "sido_full": sido_full, "sido": sido, "sigungu": sigungu,
        "road": road, "addr_detail": addr_detail, "addr": remaining,
    }, None


def parse_facilities(raw) -> list[str]:
    if pd.isna(raw) or not str(raw).strip():
        return []
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    return [FACILITY_MAP.get(p, p) for p in parts]


def make_slug(name: str) -> str:
    s = unicodedata.normalize("NFC", name)
    return re.sub(r"[^\w가-힣]", "", s)


def variant_index(name: str, section: str, n: int = VARIANT_COUNT) -> int:
    h = hashlib.sha256(f"{name}:{section}".encode("utf-8")).hexdigest()
    return int(h, 16) % n


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)["site"]
    start_date = datetime.fromisoformat(config["publish"]["start_date"]).date()

    # Hugo는 data/ 아래 yaml만 .Site.Data 로 읽으므로 config/site.yaml 원본을 그대로 복제한다.
    # (관리 지점은 config/site.yaml 하나. 이 파일은 매 실행마다 갱신되는 생성물)
    import shutil
    shutil.copyfile(CONFIG_PATH, f"{ROOT}/data/site.yaml")

    df = pd.read_excel(XLSX_PATH)
    df.columns = [c.strip() for c in df.columns]

    errors: list[dict] = []
    phone_warnings: list[str] = []
    records: list[dict] = []

    for i, row in df.iterrows():
        excel_row_no = i + 1  # 1-based, top=1
        name = clean_name(row["장례식장명"])
        addr_info, addr_err = parse_address(row["주소"])
        if addr_err:
            errors.append({"row": excel_row_no, "name": name, "reason": addr_err})
            continue
        tel, tel_warn = clean_phone(row["전화번호"])
        if tel_warn:
            phone_warnings.append(f"row {excel_row_no} ({name}): {tel_warn}")
        facilities = parse_facilities(row["시설"])

        records.append({
            "id": excel_row_no,
            "name": name,
            "addr": addr_info["addr"],
            "addr_detail": addr_info["addr_detail"],
            "sido": addr_info["sido"],
            "sido_full": addr_info["sido_full"],
            "sigungu": addr_info["sigungu"],
            "tel": tel,
            "facilities": facilities,
        })

    # slug 배정 + 중복 해소
    seen: dict[str, int] = {}
    for r in records:
        base = make_slug(r["name"])
        if base not in seen:
            seen[base] = 1
            r["slug"] = base
            continue
        candidate = f"{base}-{r['sigungu']}"
        candidate = re.sub(r"[^\w가-힣-]", "", candidate)
        if candidate not in seen:
            seen[candidate] = 1
            r["slug"] = candidate
            continue
        seen[base] += 1
        n = seen[base]
        candidate2 = f"{candidate}-{n}"
        while candidate2 in seen:
            n += 1
            candidate2 = f"{candidate}-{n}"
        seen[candidate2] = 1
        r["slug"] = candidate2
    for r in records:
        r["url"] = f"/funeral/{r['slug']}/"

    # 발행일 배정: 엑셀 마지막 행부터 역순, 하루 30개
    total = len(records)
    for r in records:
        slot_seq = total - r["id"]  # id=마지막행 -> slot_seq=0 (Day1 첫 페이지)
        day = slot_seq // PER_DAY + 1
        i_in_day = slot_seq % PER_DAY
        publish_dt = (
            datetime.combine(start_date, datetime.min.time())
            + timedelta(days=day - 1, hours=BASE_HOUR, minutes=i_in_day * INTERVAL_MIN)
        )
        r["publish_day"] = day
        r["publish_at"] = publish_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # 변형 배정 (hash 기반, 결정론적)
    for r in records:
        r["variant"] = {s: variant_index(r["name"], s) for s in VARIANT_SECTIONS}

    # 인근 장례식장: 같은 시군구 우선, 발행일 오름차순 -> 이름순, 최대 5개. 부족하면 같은 시도에서 채움
    by_sigungu = defaultdict(list)
    by_sido = defaultdict(list)
    for r in records:
        by_sigungu[(r["sido"], r["sigungu"])].append(r)
        by_sido[r["sido"]].append(r)

    def sort_key(r):
        return (r["publish_at"], r["name"])

    for r in records:
        same_sigungu = sorted(
            [x for x in by_sigungu[(r["sido"], r["sigungu"])] if x is not r],
            key=sort_key,
        )
        nearby = same_sigungu[:5]
        if len(nearby) < 5:
            chosen_slugs = {x["slug"] for x in nearby} | {r["slug"]}
            same_sido = sorted(
                [x for x in by_sido[r["sido"]] if x["slug"] not in chosen_slugs],
                key=sort_key,
            )
            nearby += same_sido[: 5 - len(nearby)]
        r["nearby"] = [x["slug"] for x in nearby]

    # 최종 스키마 순서 정리 + 원본 컬럼(sido_full 등 내부 파싱용 필드는 유지)
    for r in records:
        r.pop("addr_detail_raw", None)

    with open(OUT_FUNERALS, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # areas.json: 시도 -> 시군구 -> 개수
    areas: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        areas[r["sido"]][r["sigungu"]] += 1
    areas_out = {sido: dict(sorted(sg.items())) for sido, sg in sorted(areas.items())}
    with open(OUT_AREAS, "w", encoding="utf-8") as f:
        json.dump(areas_out, f, ensure_ascii=False, indent=2)

    if errors:
        with open(OUT_ERRORS, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["row", "name", "reason"])
            w.writeheader()
            w.writerows(errors)
    else:
        import os
        if os.path.exists(OUT_ERRORS):
            os.remove(OUT_ERRORS)

    facility_types = sorted({f for r in records for f in r["facilities"]})
    slug_dupe_check = len(seen) == len({r["slug"] for r in records})
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(f"총 입력 행: {len(df)}\n")
        f.write(f"성공 파싱: {len(records)}\n")
        f.write(f"주소 파싱 실패(_errors.csv): {len(errors)}\n")
        f.write(f"전화번호 경고: {len(phone_warnings)}건\n")
        for w in phone_warnings:
            f.write(f"  - {w}\n")
        f.write(f"\nslug 중복 없음: {slug_dupe_check}\n")
        f.write(f"발행일 범위: {records[-1]['publish_at']} ~ {records[0]['publish_at']}\n" if records else "")
        f.write(f"\n시도별 분포:\n")
        for sido, sg in areas_out.items():
            f.write(f"  {sido}: {sum(sg.values())}건 ({len(sg)}개 시군구)\n")
        f.write(f"\n시설 종류({len(facility_types)}개): {', '.join(facility_types)}\n")

    print(f"OK: {len(records)}/{len(df)} rows -> {OUT_FUNERALS}, {OUT_AREAS}")
    print(f"errors={len(errors)}, phone_warnings={len(phone_warnings)}")


if __name__ == "__main__":
    main()
