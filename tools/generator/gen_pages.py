"""data/funerals.json, data/areas.json -> content/funeral/*.md, content/area/**/_index.md

실행: python tools/generator/gen_pages.py [--limit N] [--force]
- idempotent: 매번 content/funeral/, content/area/ 를 전량 삭제 후 재생성한다.
- content/guide/, content/page/ 는 절대 건드리지 않는다.
"""
import argparse
import hashlib
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import yaml
from jinja2 import Template

sys.path.insert(0, str(Path(__file__).parent))
from build_data import variant_index  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA_FUNERALS = ROOT / "data/funerals.json"
DATA_AREAS = ROOT / "data/areas.json"
CONFIG_PATH = ROOT / "config/site.yaml"
TEMPLATES = ROOT / "tools/generator/templates"
CONTENT_FUNERAL = ROOT / "content/funeral"
CONTENT_AREA = ROOT / "content/area"

FACILITY_SENTENCES = {
    "주차장": "장례식장 내 주차장이 마련되어 있어 조문객 차량 이용이 가능합니다. 화환 배송 차량도 주차장 진입로를 통해 접근합니다.",
    "식당": "빈소 이용객을 위한 식당이 운영되고 있습니다.",
    "매점": "매점이 있어 조문에 필요한 물품을 현장에서 구매할 수 있습니다.",
    "장애인 편의시설": "장애인 편의시설이 갖춰져 있습니다.",
    "유족대기실": "유족을 위한 대기실이 마련되어 있습니다.",
    "(시설 정보 없음)": "시설 정보는 장례식장에 직접 문의하시기 바랍니다.",
}

TITLE_LETTERS = ["A", "B", "C", "D", "E"]


def title_patterns(name: str, sigungu: str, phone: str) -> dict[str, str]:
    return {
        "A": f"{sigungu} {name} 근조화환 배달 | 당일배송 · 24시간 접수 | 꽃이랑",
        "B": f"{sigungu} {name} 근조화환 가격 및 주문 안내 — 꽃이랑 {phone}",
        "C": f"{sigungu} {name} 근조화환 · 조화 배달 | 꽃이랑",
        "D": f"{sigungu} {name} 화환 주문 | 근조화환 당일배송 안내 | 꽃이랑",
        "E": f"{sigungu} {name} 근조화환 | 리본 문구 · 가격 · 배송시간 안내",
    }


def pick_title(name: str, sigungu: str, phone: str) -> str:
    idx = variant_index(name, "title", 5)
    patterns = title_patterns(name, sigungu, phone)
    title = patterns[TITLE_LETTERS[idx]]
    if len(title) > 60:
        title = patterns["A"]
    if len(title) > 60:
        title = f"{name} 근조화환 배달 | 꽃이랑"  # 최후 폴백 (매우 긴 복합 시군구명)
    return title


def addr_tail(addr: str, sigungu: str) -> str:
    """같은 이름 + 같은 시군구인 잔여 충돌 해소용: 시군구 뒤 도로명 부분."""
    return addr.split(sigungu, 1)[-1].strip() if sigungu in addr else addr


def dedupe_titles(rows: list[dict]) -> None:
    """이름이 같은 장례식장이 다른 지역에 있어 title/description 이 우연히 겹치는 경우를 해소한다."""
    for key in ("title", "description"):
        counts = Counter(row["front"][key] for row in rows)
        for row in rows:
            if counts[row["front"][key]] <= 1:
                continue
            tail = addr_tail(row["r"]["addr"], row["r"]["sigungu"])
            candidate = f"{row['front'][key]} ({tail})" if tail else row["front"][key]
            if key == "title" and len(candidate) > 60:
                candidate = f"{row['front'][key][:50]}… ({row['r']['id']})"
            row["front"][key] = candidate


def area_slug(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def parse_variants(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"\[변형\s*\d+\]", text)[1:]
    out = []
    for p in parts:
        p = re.sub(r"\n?-{3,}\s*$", "", p.strip()).strip()
        out.append(p)
    return out


def parse_faq_block(block: str) -> list[dict[str, str]]:
    qas = []
    for chunk in re.split(r"\n\s*\n", block.strip()):
        lines = [ln.strip() for ln in chunk.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        q = re.sub(r"^Q:\s*", "", lines[0])
        a = re.sub(r"^A:\s*", "", lines[1])
        qas.append({"q": q, "a": a})
    return qas


def order_facilities(name: str, facilities: list[str]) -> list[str]:
    return sorted(facilities, key=lambda f: hashlib.sha256(f"{name}:{f}".encode()).hexdigest())


def yaml_front_matter(data: dict) -> str:
    body = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
    return f"---\n{body}---\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import json
    funerals = json.loads(DATA_FUNERALS.read_text(encoding="utf-8"))
    with open(CONFIG_PATH, encoding="utf-8") as f:
        site = yaml.safe_load(f)["site"]

    if args.limit:
        funerals = funerals[: args.limit]

    if CONTENT_FUNERAL.exists() and not args.force and not args.limit:
        ans = input(f"{CONTENT_FUNERAL} 이(가) 이미 존재합니다. 전량 삭제 후 재생성할까요? [y/N] ")
        if ans.strip().lower() != "y":
            print("취소됨")
            return

    variants = {name: parse_variants(TEMPLATES / f"{name}.txt") for name in ("intro", "delivery", "order", "outro", "faq")}
    area_intro_variants = parse_variants(TEMPLATES / "area_intro.txt")

    if CONTENT_FUNERAL.exists():
        shutil.rmtree(CONTENT_FUNERAL)
    CONTENT_FUNERAL.mkdir(parents=True, exist_ok=True)
    if not args.limit and CONTENT_AREA.exists():
        shutil.rmtree(CONTENT_AREA)
    CONTENT_AREA.mkdir(parents=True, exist_ok=True)

    ctx_common = {
        "phone": site["phone"],
        "cutoff": site["delivery"]["cutoff"],
        "payment": site["delivery"]["payment"],
        "refund_policy": site["delivery"]["refund_policy"],
    }

    rows = []
    for r in funerals:
        name, sido, sigungu = r["name"], r["sido"], r["sigungu"]
        ctx = {**ctx_common, "name": name, "sido": sido, "sigungu": sigungu, "addr": r["addr"], "tel": r["tel"]}

        def render(section: str) -> str:
            v = variants[section][r["variant"][section]]
            return Template(v).render(**ctx)

        faq_block = variants["faq"][r["variant"]["faq"]]
        faq_qas = parse_faq_block(faq_block)
        faq_rendered = [{"q": Template(qa["q"]).render(**ctx), "a": Template(qa["a"]).render(**ctx)} for qa in faq_qas]

        facility_sentences = [FACILITY_SENTENCES.get(f, f"{f}가 마련되어 있습니다.") for f in order_facilities(name, r["facilities"])]

        front = {
            "title": pick_title(name, sigungu, site["phone"]),
            "description": f"{name}({sido} {sigungu}) 근조화환 배달. 가격·리본 문구·배송 소요시간 안내. 24시간 주문 접수 {site['phone']}.",
            "date": r["publish_at"],
            "lastmod": r["publish_at"],
            "url": r["url"],
            "type": "funeral",
            "funeral": {
                "name": name,
                "addr": r["addr"],
                "tel": r["tel"],
                "sido": sido,
                "sigungu": sigungu,
                "sigungu_slug": area_slug(sigungu),
                "slug": r["slug"],
                "facilities": r["facilities"],
                "facility_sentences": facility_sentences,
                "nearby": r["nearby"],
                "intro": render("intro"),
                "delivery_text": render("delivery"),
                "order_text": render("order"),
                "outro_text": render("outro"),
                "faq": faq_rendered,
            },
            "keywords": [f"{name} 근조화환", f"{name} 근조화환 가격", f"{sigungu} 장례식장 꽃배달"],
        }
        rows.append({"r": r, "front": front})

    dedupe_titles(rows)
    for row in rows:
        r, front = row["r"], row["front"]
        (CONTENT_FUNERAL / f"{r['slug']}.md").write_text(yaml_front_matter(front) + "\n", encoding="utf-8")

    # 지역 허브: areas.json (시도 -> 시군구 -> 개수)
    areas = json.loads(DATA_AREAS.read_text(encoding="utf-8"))
    by_sigungu_min_date = {}
    by_sido_min_date = {}
    for r in funerals:
        key = (r["sido"], r["sigungu"])
        by_sigungu_min_date[key] = min(by_sigungu_min_date.get(key, r["publish_at"]), r["publish_at"])
        by_sido_min_date[r["sido"]] = min(by_sido_min_date.get(r["sido"], r["publish_at"]), r["publish_at"])

    for sido, sigungu_map in areas.items():
        if args.limit and sido not in {r["sido"] for r in funerals}:
            continue
        sido_dir = CONTENT_AREA / sido
        sido_dir.mkdir(parents=True, exist_ok=True)
        sido_front = {
            "title": f"{sido} 장례식장 근조화환 배달",
            "description": f"{sido} 지역 장례식장 근조화환 배달 안내. 시군구별 장례식장 목록과 가격, 주문 방법을 확인하실 수 있습니다.",
            "date": by_sido_min_date.get(sido, site["publish"]["start_date"]),
            "url": f"/area/{sido}/",
            "type": "area",
            "area": {"level": "sido", "sido": sido},
        }
        (sido_dir / "_index.md").write_text(yaml_front_matter(sido_front) + "\n", encoding="utf-8")

        for sigungu in sigungu_map:
            if args.limit and (sido, sigungu) not in by_sigungu_min_date:
                continue
            sg_slug = area_slug(sigungu)
            sg_dir = sido_dir / sg_slug
            sg_dir.mkdir(parents=True, exist_ok=True)
            intro_idx = variant_index(f"{sido}{sigungu}", "area_intro", 5)
            intro_text = Template(area_intro_variants[intro_idx]).render(sido=sido, sigungu=sigungu)
            sg_front = {
                "title": f"{sigungu} 장례식장 근조화환 배달",
                "description": f"{sido} {sigungu} 장례식장 근조화환 배달 안내. 장례식장별 가격과 주문 방법을 확인하실 수 있습니다.",
                "date": by_sigungu_min_date.get((sido, sigungu), site["publish"]["start_date"]),
                "url": f"/area/{sido}/{sg_slug}/",
                "type": "area",
                "area": {"level": "sigungu", "sido": sido, "sigungu": sigungu, "sigungu_slug": sg_slug, "intro_text": intro_text},
            }
            (sg_dir / "_index.md").write_text(yaml_front_matter(sg_front) + "\n", encoding="utf-8")

    print(f"OK: funeral {len(funerals)}개, area 시도 {len(areas)}개 생성")


if __name__ == "__main__":
    main()
