# rppg-web 도입 영향 범위

## 목표

`imagine` 구간의 영상은 브라우저 안에서만 처리한다. 프론트엔드는
`@elata-biosciences/rppg-web`이 산출한 BPM과 품질 요약만 서버로 보내고,
서버는 이를 기존 `HeartRateFeatures` 파이프라인에 연결한다.

이 변경은 STT/음성 분석 경로를 건드리지 않는다.

## 계약과 호환 전략

- `Capture.rppg_measurement`를 선택 필드로 추가한다.
- 새 프론트엔드는 `imagine` 캡처에 `rppg_measurement`를 보내고
  `rgb_series`는 보내지 않는다.
- 백엔드는 `rppg_measurement`가 있으면 이를 우선 사용한다.
- `rppg_measurement`가 없으면 기존 `rgb_series + fps` 분석을 계속 지원한다.
  기존 저장 세션, API 호출자, 병렬 브랜치를 깨뜨리지 않기 위한 임시 호환 경로다.
- `speak` 캡처와 오디오/STT 계약은 변경하지 않는다.

`rppg_measurement`에는 원본 프레임이나 RGB 샘플을 포함하지 않는다. BPM,
confidence, signal quality, estimator agreement, reason code와 안정 샘플 수만
포함한다. 측정 시간은 바깥 `Capture.duration_sec` 하나로 관리한다. 패키지의
`snr` 단위가 현재 서버의 `snr_db` 계약과 같다고
보장할 수 없으므로 서로 매핑하지 않는다.

## 프론트엔드 동작

- 패키지 버전은 `0.14.0`으로 고정한다. 아직 1.0 이전이므로 무의식적인 minor
  업데이트로 계약이 바뀌는 일을 막는다.
- Vite에서는 패키지의 JS glue와 WASM 파일을 `?url`로 명시적으로 import한다.
- 카메라가 준비되면 rPPG 세션을 한 번 시작해 워밍업 비용을 공유한다.
- 15초 `imagine` 구간 동안 UI는 계속 품질 안내를 표시한다.
- 측정 중 BPM 숫자는 보여주지 않는다. 숫자를 본 반응이 현재 측정과 다음 선택지에
  영향을 주지 않도록 얼굴·조명·움직임 안내와 측정 신뢰도만 표시한다.
- 패키지의 롤링 윈도우가 약 10초이므로, 앞선 발화의 얼굴 움직임이 빠져나간
  마지막 3초의 publish 가능한 스냅샷을 집계한다.
- 안정된 스냅샷이 없으면 억지 BPM을 만들지 않고 측정값을 `null`로 보낸다.
  분석 단계는 그 심박 축을 제외하고 음성 등 사용 가능한 신호만 사용한다.
- rPPG 초기화가 실패해도 전체 세션을 중단하지 않는다. 사용자는 음성 경로로
  계속 진행할 수 있고 UI에는 심박 측정 불가 상태를 표시한다.

세션을 계속 유지하면 tracker의 시간적 상태가 다음 선택지로 이어질 수 있다.
이번 MVP에서는 10초 워밍업 때문에 구간마다 재생성하는 것보다 안정성이 낫다고
판단한다. 선택지 간 독립성이 더 중요하다는 실측 결과가 나오면 SDK의 reset 지원
또는 구간 길이 증가와 함께 다시 결정한다.

## 변경/충돌 가능 파일

| 영역 | 파일 | 영향 |
|---|---|---|
| 프론트 캡처 | `frontend/src/hooks/useSessionFlow.ts` | 기존 ROI 샘플러를 rppg-web 세션으로 교체 |
| 프론트 어댑터 | `frontend/src/lib/rppg.ts` | 세션 수명, UI 품질, 후반부 측정 집계 |
| API 계약 | `frontend/src/types/contracts.ts` | 선택형 `rppg_measurement` 추가 |
| 의존성 | `frontend/package.json`, lockfile | rppg-web 0.14.0 고정 |
| 백엔드 계약 | `backend/app/schemas/capture.py` | 선택형 클라이언트 측정 모델 추가 |
| 특징 추출 | `backend/app/services/feature_service.py` | 클라이언트 결과 우선, 기존 RGB 폴백 유지 |
| 계약 문서 | `docs/CONTRACTS.md` | 프라이버시 및 양쪽 입력 경로 명시 |

`useSessionFlow.ts`와 캡처 계약은 팀원의 캡처/STT 작업과 충돌하기 쉬운 지점이다.
병합할 때 음성 분기의 최신 변경을 보존하고 `imagine` 분기만 선택적으로 적용한다.

## 검증 현황과 롤백

- [x] 프론트엔드 TypeScript 검사와 production build
- [x] Vite 6 빌드 결과에 JS glue와 WASM 자산 포함
- [x] 백엔드 전체 테스트 105개 통과
- [x] 클라이언트 측정값을 `HeartRateFeatures`로 변환하는 서비스 테스트
- [x] 낮은 confidence가 기존 규칙대로 BPM을 판정에서 제외하는 테스트 유지
- [x] 기존 RGB 시계열 E2E 테스트를 유지해 호환 경로 확인
- [x] 실제 `/captures` 요청에 대한 새 계약 통합 테스트
- [x] 실제 브라우저에서 WASM 로드, 얼굴 안내, 10초 이후 내부 측정값 생성 확인
- [x] 개발 전용 비저장 비교 API와 `/rppg-test` 교대 측정 화면
- [x] 1인 기준 장비 비교: rppg-web 성공값 MAE 2.96 BPM, CHROM 4/4 confidence 미달
- [ ] 네트워크 요청에 영상/RGB가 없고 `rppg_measurement`만 있는지 확인

비교 프로토콜과 원자료, 해석 범위는 `docs/RPPG_TESTING.md`에 기록한다. 현재 실측은
참가자 1명·조건 1개의 탐색 결과이므로 일반 정확도 근거로 사용하지 않는다.

문제가 생기면 새 프론트엔드 어댑터와 `rppg_measurement` 전송만 되돌려도 서버의
기존 RGB 분석 경로로 즉시 복귀할 수 있다.
