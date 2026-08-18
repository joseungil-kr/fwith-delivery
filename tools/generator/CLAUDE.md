# 생성기

- 모든 스크립트는 idempotent. 두 번 실행해도 같은 결과.
- 출력 경로는 프로젝트 루트 기준 상대경로. 절대경로 하드코딩 금지.
- 실행 순서: build_data.py → gen_pages.py → verify.py
- 데이터 파싱 실패는 조용히 넘기지 말고 `_errors.csv` 로 남기고 stderr 경고.
- 추정·보간 금지. 원본에 없는 값을 만들어내지 않는다.
