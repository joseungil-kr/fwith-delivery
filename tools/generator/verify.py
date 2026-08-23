"""content/funeral, content/area, config/site.yaml, public/ 검수. (§16)

실행: python tools/generator/verify.py
- 실패 항목이 있으면 exit code 1. 통과하면 0.
- public/ 기반 체크는 마지막 hugo build 결과를 그대로 검사한다.
  (buildFuture=false 라 발행일이 지난 페이지만 존재할 수 있음 — 개수는 별도 표기)
"""
import itertools
import random
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CONTENT_FUNERAL = ROOT / "content/funeral"
CONTENT_AREA = ROOT / "content/area"
CONFIG_PATH = ROOT / "config/site.yaml"
PUBLIC = ROOT / "public"

PER_DAY = 30
TOTAL_DAYS = 36
REQUIRED_KEYS = {"title", "description", "date", "url", "type", "funeral"}

failures: list[str] = []
warnings: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def load_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def ngrams(text: str, n=3) -> set:
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def main():
    # ---------- 구조 ----------
    md_files = sorted(CONTENT_FUNERAL.glob("*.md"))
    check("content/funeral/*.md 개수 == 1080", len(md_files) == 1080, f"{len(md_files)}개")

    fms = [load_front_matter(p) for p in md_files]
    urls = [fm.get("url") for fm in fms]
    dup_urls = [u for u, c in Counter(urls).items() if c > 1]
    check("url 중복 0건", not dup_urls, f"중복 {len(dup_urls)}건")

    missing_keys = [fm.get("url", "?") for fm in fms if not REQUIRED_KEYS.issubset(fm.keys())]
    check("front matter 필수 키 누락 0건", not missing_keys, f"{len(missing_keys)}건")

    with open(CONFIG_PATH, encoding="utf-8") as f:
        site = yaml.safe_load(f)["site"]
    start_date = site["publish"]["start_date"]
    dates = sorted(fm.get("date", "") for fm in fms)
    in_range = all(start_date <= d[:10] for d in dates)
    check("date 가 START_DATE 이후 범위 내", in_range)

    day_counts = Counter(fm.get("date", "")[:10] for fm in fms)
    per_day_ok = len(day_counts) == TOTAL_DAYS and all(v == PER_DAY for v in day_counts.values())
    check("하루당 페이지 수 정확히 30개 x 36일", per_day_ok, f"{len(day_counts)}일 분포")

    # ---------- SEO (front matter 기준) ----------
    long_titles = [fm["title"] for fm in fms if len(fm.get("title", "")) > 60]
    check("title 길이 <= 60자", not long_titles, f"{len(long_titles)}건 초과")

    bad_desc = [fm["url"] for fm in fms if not (40 <= len(fm.get("description", "")) <= 150)]
    check("description 길이 40~150자", not bad_desc, f"{len(bad_desc)}건")

    dup_titles = [t for t, c in Counter(fm.get("title") for fm in fms).items() if c > 1]
    check("동일 title 0건", not dup_titles, f"{len(dup_titles)}종 중복")

    dup_desc = [d for d, c in Counter(fm.get("description") for fm in fms).items() if c > 1]
    check("동일 description 0건", not dup_desc, f"{len(dup_desc)}종 중복")

    facility_variants = {tuple(fm["funeral"].get("facility_sentences", [])) for fm in fms}
    check("시설 문단 고유 조합 >= 30", len(facility_variants) >= 30, f"{len(facility_variants)}종")

    # ---------- 중복도 (본문 텍스트 3-gram Jaccard, front matter 변형 텍스트 기준) ----------
    bodies = []
    for fm in fms:
        fu = fm.get("funeral", {})
        parts = [fu.get("intro", ""), fu.get("delivery_text", ""), fu.get("order_text", ""), fu.get("outro_text", "")]
        bodies.append(" ".join(parts))
    sample = random.Random(42).sample(range(len(bodies)), min(200, len(bodies)))
    pairs = list(itertools.islice(itertools.combinations(sample, 2), 100))
    scores = [jaccard(ngrams(bodies[i]), ngrams(bodies[j])) for i, j in pairs]
    avg_sim = sum(scores) / len(scores) if scores else 0
    check("무작위 100쌍 3-gram Jaccard 평균 < 0.75", avg_sim < 0.75, f"{avg_sim:.3f}")

    # ---------- 법적 ----------
    site_text = CONFIG_PATH.read_text(encoding="utf-8")
    placeholders = re.findall(r"\{\{[A-Z_]+\}\}", site_text)
    check("config/site.yaml 에 {{PLACEHOLDER}} 잔존 0건", not placeholders, f"{placeholders}")

    # ---------- public/ 기반 (있는 만큼만 검사) ----------
    html_files = sorted(PUBLIC.glob("funeral/*/index.html")) if PUBLIC.exists() else []
    if not html_files:
        warnings.append("public/funeral/*/index.html 없음 — hugo build 먼저 실행할 것")
        print("[WARN] public/ 빌드 결과 없음 — HTML 기반 체크 스킵")
    else:
        print(f"(public/funeral 아래 {len(html_files)}개 페이지로 HTML 체크 진행 — buildFuture=false 이므로 전체 1080건이 아닐 수 있음)")
        h1_bad, short_body, canonical_bad, cdn_refs, size_total = [], [], [], [], 0
        for p in html_files:
            html = p.read_text(encoding="utf-8")
            size_total += len(html.encode("utf-8"))
            if len(re.findall(r"<h1[ >]", html)) != 1:
                h1_bad.append(p)
            main_html = re.search(r"<main[^>]*>(.*)</main>", html, re.S)
            body_text = strip_tags(main_html.group(1)) if main_html else ""
            if len(body_text) < 900:
                short_body.append(p)
            canonical = re.search(r'<link rel=canonical href="([^"]+)', html)
            if canonical and not canonical.group(1).startswith('https://'):
                canonical_bad.append(p)
            if re.search(r'<(script|link)[^>]+(src|href)="?https?://(?!fwith\.kr)', html):
                cdn_refs.append(p)

        check("h1 페이지당 정확히 1개", not h1_bad, f"{len(h1_bad)}건")
        check("본문 텍스트 900자 이상", not short_body, f"{len(short_body)}건 미달")
        check("canonical 절대경로", not canonical_bad, f"{len(canonical_bad)}건")
        check("외부 리소스(CDN) 참조 0건", not cdn_refs, f"{len(cdn_refs)}건")

        avg_kb = (size_total / len(html_files)) / 1024
        check("평균 페이지 크기 < 45KB (gzip 전)", avg_kb < 45, f"{avg_kb:.1f}KB")

        legal_terms = ["사업자등록번호", "통신판매업신고번호", "사업장 주소", site["legal"]["biz_no"]]
        legal_bad = [p for p in html_files if not all(t in p.read_text(encoding="utf-8") for t in legal_terms)]
        check("전 페이지 푸터 사업자 정보 존재", not legal_bad, f"{len(legal_bad)}건 누락")

    print()
    if failures:
        print(f"결과: FAIL ({len(failures)}건 실패)")
        sys.exit(1)
    print("결과: PASS")


if __name__ == "__main__":
    main()
