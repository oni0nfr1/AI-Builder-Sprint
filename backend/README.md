# 직관 노트 — 백엔드

파이프라인 `[0]`~`[8]` 구현. 설계는 `../CLAUDE.md`, 계약은 `../docs/CONTRACTS.md`.

## 실행

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env        # UPSTAGE_API_KEY 채우기 (없어도 동작함)
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

API 문서: http://localhost:8000/docs

**API 키가 없어도 파이프라인 전체가 돈다.** `[0]` 고민 파싱과 `[5]` 리포트 생성은
Solar 호출이 실패하면 규칙 기반 폴백으로 넘어간다. 개발·테스트 중에는 키 없이 진행 가능.

## 테스트

```bash
./.venv/Scripts/python.exe -m pytest -q
```

## 구조

```
app/
  schemas/        계약 (docs/CONTRACTS.md 에서 파생)
    common.py       MetricKey, ApiResponse
    decision.py     [0]
    capture.py      [1]
    features.py     [2]
    analysis.py     [3][4]  ★두 축 분리
    report.py       [5][6]
    session.py      [7][8]
  services/
    rppg.py               [2] 레거시 서버 rPPG (CHROM → bandpass → FFT)
    voice.py              [2] openSMILE eGeMAPS 88, parselmouth 폴백
    feature_service.py    [2] phase/측정 출처별 디스패치
    analysis_service.py   [3][4] ★선호축/상태축
    report_service.py     [5] 산파술 프롬프트
    decision_service.py   [0]
    value_map_service.py  [8]
    llm.py                Upstage Solar
  routers/        decisions.py, sessions.py
  core/           config.py, storage.py (SQLite)
```

## 엔드포인트

| | |
|---|---|
| `POST /decisions` | `[0]` 고민 한 문장 → 선택지 2개 + 가치축 + 대칭 프롬프트 |
| `POST /sessions` | 세션 시작 |
| `POST /sessions/{id}/captures` | `[1]` 캡처 수신 → 클라이언트 rPPG 요약 또는 레거시 RGB에서 `[2]` 특징 추출 |
| `POST /sessions/{id}/analyze` | `[3][4][5]` → **Report만 반환** (Verdict는 저장만) |
| `POST /sessions/{id}/annotation` | `[6]` 사용자 태깅 |
| `POST /sessions/{id}/retrospective` | `[8]` 회고 (1주/3개월/6개월/1년) |
| `GET /value-map` | `[8]` 가치관 지도 |

## 주의

- `analyze`는 `Report`만 반환한다. **`Verdict`(내부 판정)를 클라이언트로 보내지 마라** —
  우리가 판정했다는 사실이 노출되면 사용자는 다시 결정을 아웃소싱하게 된다.
- `audio_base64`는 **16-bit PCM WAV**여야 한다. 브라우저가 WAV로 인코딩해 보낸다
  (서버에 ffmpeg 의존성을 만들지 않기 위한 계약).
- 새 rPPG 경로는 브라우저에서 계산한 `rppg_measurement`만 받는다. 영상 프레임과
  RGB 시계열은 서버로 보내지 않는다. 기존 `rgb_series + fps`는 호환 경로로 유지한다.
- rPPG `confidence`가 0.4 미만이면 심박 축이 판정에서 자동 제외된다.
