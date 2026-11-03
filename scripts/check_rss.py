"""Verify a Hugo output directory's home RSS (Python standard library only)."""
import email.utils
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

root = Path(sys.argv[1] if len(sys.argv) > 1 else "public")
raw = (root / "index.xml").read_bytes()
assert len(raw) < 10 * 1024 * 1024, "RSS exceeds 10MB"
channel = ET.fromstring(raw).find("channel")
items = channel.findall("item")
assert 0 < len(items) <= 50, "RSS must contain 1-50 public content entries"
links = [item.findtext("link") for item in items]
assert len(set(links)) == len(links), "Duplicate RSS URLs"
missing_dates = 0
for item in items:
    assert item.findtext("title"), "Missing title"
    url = item.findtext("link")
    guid = item.find("guid")
    assert guid is not None and guid.text == url and guid.get("isPermaLink") == "true"
    parsed = urlparse(url)
    assert parsed.scheme == "https" and parsed.netloc, "RSS links must be absolute HTTPS URLs"
    assert not re.search(r"/(admin|privacy|terms)(/|\.)", parsed.path, re.I)
    target = root / unquote(parsed.path).lstrip("/")
    if parsed.path.endswith("/"):
        target /= "index.html"
    assert target.is_file(), f"RSS URL absent from build: {url}"
    body = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
    assert body and re.sub(r"<[^>]+>", "", body).strip(), "Empty RSS body"
    assert item.findtext("description") == body, "RSS description must retain full content"
    assert not re.search(r'''(?:href|src|poster)=["'](?![a-z][a-z0-9+.-]*:|//)[^"']+''', body, re.I), "Relative body URL"
    if date := item.findtext("pubDate"):
        assert "0001" not in date
        assert email.utils.parsedate_to_datetime(date) <= datetime.now(timezone.utc), "Future publication date"
    else:
        missing_dates += 1
assert "application/rss+xml" in (root / "index.html").read_text(encoding="utf-8")
print(f"RSS OK: {len(items)} items, {len(raw)} bytes, {missing_dates} dates omitted")
