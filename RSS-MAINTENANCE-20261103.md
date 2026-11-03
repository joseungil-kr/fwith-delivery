# RSS maintenance — 2026-11-03

The existing /index.xml URL is preserved. Hugo's embedded RSS structure is reused with full rendered content in description and content:encoded, absolute body URLs, URL-based GUIDs, and a maximum of 50 nonempty public entries. Missing original publication dates are omitted; no content dates are invented or changed. Draft, private, noindex and future-dated entries are excluded. RSS discovery uses the home feed. Existing sitemap and publishing schedules are preserved.

Validate after a normal Hugo build: `python scripts/check_rss.py <output-directory>`. The check uses only the Python standard library. Feed generation runs on each existing build/deploy. Hugo RSS documentation: https://gohugo.io/templates/rss/ . The template follows Hugo's Apache-2.0 embedded RSS structure.

Rollback: restore the source commit and existing successful Pages deployment recorded in the task's deployment evidence. Do not change hosting, secrets, DNS, or security settings.
Previous source: 9a821ea47bc1f9145e6fb5d218b98650761c47cd
Previous successful Pages deployment: 079336f5-5bef-4119-abb2-303edc5e8d4d

