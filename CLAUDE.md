# 꽃이랑 근조화환 사이트

## 절대 규칙
1. `content/funeral/`, `content/area/` 는 100% 자동 생성물이다.
   → 개별 파일을 직접 수정하지 말 것. 반드시 `tools/generator/` 를 고쳐 재생성한다.
2. `자료/*.xlsx` 는 읽기 전용. 절대 수정·이동·삭제하지 않는다.
3. 웹폰트, 외부 JS, 외부 CSS, 광고/애널리틱스 스크립트 추가 금지.
   (분석은 Cloudflare Web Analytics — 스크립트 1KB, 필요 시 별도 승인 후)
4. 랜덤 시드 사용 금지. 모든 변형은 `hash(장례식장명)` 기반 결정론적 배정.
5. 도메인·가격·사업자정보는 `config/site.yaml` 한 곳에서만 관리. 하드코딩 금지.
6. `content/guide/`, `content/page/` 는 수기 콘텐츠. 생성 스크립트가 건드리면 안 된다.
7. 커밋 전 `python tools/generator/verify.py` 를 통과해야 한다.

## 톤
장례 맥락. 느낌표·이모지·과장 광고 표현 금지. 담담한 평서문.

## 스택
Hugo extended / Python 3.11 (pandas, openpyxl, jinja2) / Cloudflare Pages(Wrangler)
