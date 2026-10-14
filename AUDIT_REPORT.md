# 🔍 [적대적 검수 리포트] 꽃이랑 근조화환 (fwith-delivery)

## 1. 개요 및 아키텍처
- **기술 스택**: Hugo, 정적 사이트
- **도메인**: `https://fwith.kr/`
- **주요 기능**: 전국 근조화환 배송 안내 및 상품 주문

---

## 2. 보안 & 리소스 배포 치명적 결함 (Critical / High)

### 🚨 결함 1: 정적 배포 디렉터리에 3.75MB 대용량 ZIP 압축파일 방치
- **위치**: `static/images/compressed (1).zip` (3,757,665 bytes)
- **문제점**:
  1. Hugo는 `static/` 디렉터리의 모든 파일을 빌드 결과물로 복사합니다. 따라서 이 압축파일이 `https://fwith.kr/images/compressed (1).zip` 경로로 **전 세계 웹에 그대로 공개 배포**됩니다.
  2. 디렉터리 스캐너나 공격자가 원본 고해상도 자산 또는 압축파일 내의 비공개 메타데이터를 다운로드할 수 있습니다.
  3. 불필요하게 4MB에 가까운 용량이 Git 리포지토리 및 Cloudflare Pages 배포 파이프라인 대역폭을 낭비합니다.
- **조치 방안**: 즉시 해당 ZIP 파일을 리포지토리 및 `static/images/`에서 삭제해야 합니다.

### ⚠️ 결함 2: 템플릿의 파비콘 404 Not Found 에러
- **위치**: `layouts/partials/head.html` 라인 25
- **코드**:
  ```html
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  ```
- **문제점**: `static/` 폴더 내에 `favicon.svg` 파일이 **실제로 존재하지 않습니다**. 사이트에 방문하는 모든 사용자의 브라우저에서 파비콘 요청 시 404 에러가 발생합니다.
- **조치 방안**: `static/favicon.svg` 파일을 생성하거나, 기존 파비콘 파일 경로로 수정해야 합니다.

---

## 3. SEO & 구조화 데이터 점검 (Medium)
1. **OG Image 동적 분기 로직의 불안정성**:
   - `head.html` 라인 14: `{{ $heroIndex := mod (len .Permalink) 2 }}`
   - 퍼멀링크 문자열 길이에 따라 2개 이미지 중 하나를 골라 썸네일로 쓰는 로직이 적용되어 있으나, 글 성격이나 내용과 무관하게 기계적으로 배정되어 SNS 공유 시 부적절한 이미지가 노출될 위험이 있습니다.
2. **사이트맵 설정 확인**:
   - `hugo.toml`에 `enableRobotsTXT = true`는 켜져 있으나 robots.txt 내에 sitemap.xml 경로가 올바르게 인출되는지 확인이 필요합니다.

---

## 4. 긴급 보완 권고사항 체크리스트
- [ ] `static/images/compressed (1).zip` 파일 즉시 제거
- [ ] 누락된 `static/favicon.svg` 파일 생성 또는 경로 수정
- [ ] 대표 썸네일 이미지 매핑 로직 점검
