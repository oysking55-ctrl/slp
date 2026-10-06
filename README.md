# SLP — 은퇴 후 정착지 찾기 에이전트

60세 은퇴 후 살 곳을 찾기 위해 **무료로 검색할 수 있는 경매·공매·부동산 정보**를 모아서,
조건에 맞는 물건을 **웹 페이지(GitHub Pages)** 로 보여주고, 직접 조사해 본 뒤 괜찮은 곳은
**관심 목록**에 체크해 메모와 함께 저장소에 보관합니다.

```
GitHub 이슈 양식에서 조건 선택 ──▶ GitHub Actions가 검색 실행 ──▶ 결과 JSON 커밋 ──▶ 결과 페이지
 (지역·면적·토지 유형·금액·출처)      (온비드·법원경매·네이버 +            (docs/data/)        ☆ 관심 체크 → favorites.json
                                       실거래가 비교 + 생활 편의 점수)
```

## 무엇을 검색하나요

| 출처 | 내용 | 방식 | 상태 |
|---|---|---|---|
| 온비드 (캠코 공매) | 공매 토지·주택 | 공공데이터포털 공식 API | ✅ 권장 |
| 국토교통부 실거래가 | 토지·단독/다가구 매매가 | 공공데이터포털 공식 API | ✅ 물건마다 **"주변 시세의 몇 %"** 계산 |
| 법원경매정보 | 경매 물건 (향후 60일 매각기일) | 웹 화면 요청 흉내 | ⚠ 실험적 (사이트 개편·해외 IP 차단 시 실패) |
| 네이버 부동산 | 토지·단독·전원주택 매물 | 비공식 경로 | ⚠ 선택 사항. 이용약관상 자동 수집 제한, 차단될 수 있음 |
| 농지은행 · 빈집은행 | 귀농·귀촌용 농지/빈집 | — | 🔜 다음 단계 |

**생활 편의 점수 (0~100)**: 카카오 지도 API로 종합병원·병의원·약국·마트·기차역/터미널·면사무소까지
거리를 재서 계산합니다. 기준과 비중은 [`config/scoring.json`](config/scoring.json)에서 바꿀 수 있습니다.

## 처음 한 번 설정하기

### 1. 무료 API 키 받기
- **공공데이터포털** (https://www.data.go.kr) 회원가입 후 아래 3개를 *활용신청* (보통 즉시~1일 승인)
  - `한국자산관리공사_온비드 캠코공매물건 조회서비스`
  - `국토교통부_토지 매매 실거래가 자료`
  - `국토교통부_단독/다가구 매매 실거래가 자료`
  - 마이페이지의 **일반 인증키(Decoding)** 를 복사 (세 서비스 모두 같은 키)
- **카카오 개발자** (https://developers.kakao.com) → 내 애플리케이션 → 앱 만들기 → **REST API 키** 복사
  (앱 설정 → 플랫폼/제품 설정에서 '카카오맵' 사용 설정이 필요할 수 있습니다)

### 2. 저장소에 키 등록
GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
- `DATA_GO_KR_KEY` = 공공데이터포털 인증키(Decoding)
- `KAKAO_REST_KEY` = 카카오 REST API 키

### 3. 결과 페이지 켜기
**Settings → Pages** → Source: *Deploy from a branch* → Branch: 기본 브랜치(`main` 권장), 폴더: `/docs` → Save
→ 잠시 뒤 `https://<아이디>.github.io/slp/` 에서 결과 페이지가 열립니다.

### 4. Actions 쓰기 권한 확인
**Settings → Actions → General → Workflow permissions** → *Read and write permissions* 선택.

### 5. (관심 저장용) GitHub 토큰
결과 페이지의 **설정** 탭 안내대로 *Fine-grained token* 을 만들어 붙여넣습니다
(이 저장소만, `Contents: Read and write`). 토큰은 그 브라우저에만 보관됩니다.
휴대폰·PC 각각 한 번씩 입력하면 어디서든 같은 관심 목록이 보입니다.

## 사용법

1. 결과 페이지의 **+ 새 검색** (또는 GitHub **Issues → New issue → 🔎 정착지 매물 검색**)
2. 시도·시군구, 토지 유형, 면적(평/㎡), 금액(예: `3억`, `1억 5000`), 출처를 고르고 **Submit**
3. 몇 분 뒤 이슈에 요약 댓글이 달리고, 결과 페이지에 새 검색이 추가됩니다
4. 결과를 보며 **카카오맵·네이버지도·토지이음** 링크로 직접 조사 → 괜찮으면 **☆ 관심**
5. **관심 목록** 탭에서 상태(검토중/현장답사 예정/유력/보류…), 별점, 조사 메모 기록 · CSV 내려받기

조건을 바꾸려면 이슈 본문을 **Edit** 하면 다시 검색합니다. 저장소 주인이 연 이슈만 검색이 실행됩니다.

## 주의 사항
- 이 저장소는 **공개(public)** 이므로 검색 결과와 관심 목록·메모도 공개됩니다.
  개인적인 메모를 남길 계획이면 저장소를 비공개로 바꾸는 것을 고려하세요 (비공개 저장소의 Pages는 유료 플랜 필요).
- 경매·공매 정보는 참고용입니다. 입찰 전에는 반드시 원문 공고, 등기부등본, 토지이용계획(토지이음), 현장을 확인하세요.
- 2026년 인천·화성 등 최근 행정구역 개편은 `config/regions.json`에 아직 반영되지 않았을 수 있습니다 (직접 수정 가능).

## 개발자용

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                                   # 테스트
DATA_GO_KR_KEY=... KAKAO_REST_KEY=... \
python -m slp search --issue-body tests/fixtures/issue_body.md   # 로컬에서 검색 실행
cd docs && python -m http.server         # http://localhost:8000 에서 결과 페이지 확인
```

| 경로 | 역할 |
|---|---|
| `slp/criteria.py` | 이슈 양식 → 검색 조건 |
| `slp/sources/` | 출처별 수집기 (`onbid`, `court`, `naver`, `molit`) |
| `slp/filtering.py` · `market.py` · `scoring.py` | 공통 필터 · 실거래가 비교 · 생활 편의 점수 |
| `slp/search.py` | 전체 실행 · 결과 저장 · 이슈 댓글 요약 |
| `docs/` | 결과 페이지 (GitHub Pages), `docs/data/` 에 결과·관심 목록 |
| `.github/ISSUE_TEMPLATE/search.yml` | 검색 조건 양식 |
| `.github/workflows/search.yml` | 이슈 → 검색 → 커밋 → 댓글 |
| `config/regions.json` | 시도·시군구 코드 (`scripts/build_regions.py`로 생성) |
