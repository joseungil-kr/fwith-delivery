"""public/sitemap.xml 의 신규 URL만 골라 IndexNow 에 제출한다. (§13.3)

실행: python tools/generator/indexnow.py
- 이미 .indexnow/submitted.txt 에 있는 URL은 다시 보내지 않는다.
- 신규 URL이 0건이면 아무 것도 하지 않고 종료한다 (0건 POST 금지).
- 성공(200/202) 한 요청만 submitted.txt 에 기록한다. 실패분은 다음 실행 때 재시도된다.
"""
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
SITEMAP = ROOT / "public/sitemap.xml"
SUBMITTED = ROOT / ".indexnow/submitted.txt"
CONFIG_PATH = ROOT / "config/site.yaml"

MAX_PER_REQUEST = 10000
SLEEP_BETWEEN_ENDPOINTS = 3


def main():
    if not SITEMAP.exists():
        print(f"에러: {SITEMAP} 없음. 먼저 hugo build 를 실행할 것", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        site = yaml.safe_load(f)["site"]
    domain = site["domain"]
    key = site["indexnow"]["key"]
    endpoints = site["indexnow"]["endpoints"]

    sitemap_xml = SITEMAP.read_text(encoding="utf-8")
    current = set(re.findall(r"<loc>(.*?)</loc>", sitemap_xml))

    SUBMITTED.parent.mkdir(parents=True, exist_ok=True)
    submitted = set(SUBMITTED.read_text(encoding="utf-8").splitlines()) if SUBMITTED.exists() else set()

    new_urls = sorted(current - submitted)
    if not new_urls:
        print("신규 URL 없음. 종료")
        return

    print(f"신규 URL {len(new_urls)}건 제출 시작")
    key_location = f"https://{domain}/{key}.txt"

    ok_urls = set()
    for batch_start in range(0, len(new_urls), MAX_PER_REQUEST):
        batch = new_urls[batch_start:batch_start + MAX_PER_REQUEST]
        payload = {"host": domain, "key": key, "keyLocation": key_location, "urlList": batch}
        for i, endpoint in enumerate(endpoints):
            try:
                resp = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if resp.status_code in (200, 202):
                    print(f"OK {endpoint}: {resp.status_code}")
                    ok_urls.update(batch)
                else:
                    print(f"FAIL {endpoint}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            except requests.RequestException as e:
                print(f"FAIL {endpoint}: {e}", file=sys.stderr)
            if i < len(endpoints) - 1:
                time.sleep(SLEEP_BETWEEN_ENDPOINTS)

    if ok_urls:
        with open(SUBMITTED, "a", encoding="utf-8") as f:
            for u in sorted(ok_urls):
                f.write(u + "\n")
        print(f"submitted.txt 에 {len(ok_urls)}건 기록")


if __name__ == "__main__":
    main()
