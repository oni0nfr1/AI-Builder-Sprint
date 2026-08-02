# 파이프라인 계약 (Contracts)

파이프라인 각 단계의 입출력 정의. **이 문서가 단일 진실 소스**이고, backend pydantic 스키마와 frontend TS 타입은 여기서 파생된다.

계약만 지키면 각 단계의 안쪽 구현은 통째로 갈아끼울 수 있다 — 이게 "골조 먼저, 단계별 수정" 전략의 전제다.

```
[0] 고민 등록 → Decision
[1] 캡처      → Capture
[2] 특징 추출 → Features
[3] 상대화    → Delta          ★선호축과 상태축 분리
[4] 판정      → Verdict
[5] 리포트    → Report
[6] 태깅      → Annotation
[7] 저장      → Session
[8] 축적      → Retrospective / ValueMap
```

---

## 공통 규약

### 지표 키 (METRIC_KEYS)

Delta 계산에 쓰이는 표준 키. 모든 단계가 같은 이름을 쓴다.

| 키 | 출처 | 방향 해석 |
|---|---|---|
| `f0_mean` | 음성 | 피치 평균 |
| `f0_std` | 음성 | 피치 변동폭 |
| `loudness_mean` | 음성 | 음량 |
| `jitter_local` | 음성 | 주파수 미세 떨림 |
| `shimmer_local` | 음성 | 진폭 미세 떨림 |
| `hnr` | 음성 | 배음 대 잡음비 (낮을수록 거친 목소리) |
| `speech_rate` | 음성 | 말속도 |
| `pause_ratio` | 음성 | 침묵 비율 |
| `bpm` | 심박 | 심박수 |

> `hrv_rmssd`는 웨어러블 연동 시 추가. MVP(웹캠 rPPG)에서는 산출하지 않는다.

### Delta 값의 단위

모든 delta는 **비율(ratio)** 이다. `0.18` = 18% 높음, `-0.12` = 12% 낮음.
절대치는 쓰지 않는다 — 사람마다 타고난 기준이 다르기 때문.

### API 응답 래퍼

```json
{ "ok": true, "data": { }, "error": null }
```
실패: `{ "ok": false, "data": null, "error": { "code": "...", "message": "..." } }`

---

## [0] Decision — 고민 등록

`POST /decisions`

```ts
Decision {
  id: string
  raw_input: string          // 사용자가 말/쓴 원문
  title: string              // LLM 정규화: "이직할지 말지"
  value_axis: string         // LLM 추출: "안정 vs 성장"  → [8] 가치관 지도의 축
  options: Option[]          // MVP는 2개
  created_at: datetime
}

Option {
  id: string
  label: string              // "현 직장 유지"
  imagine_prompt: string     // "현 직장에 남은 6개월 뒤의 당신을 상상해보세요"
  speak_prompt: string       // "그때 떠오르는 걸 말해주세요"
  order_index: int           // ★실제 제시 순서 (랜덤화 결과를 기록) — Q1 순서 효과
}
```

**주의**: `imagine_prompt`/`speak_prompt`는 LLM이 생성한다. 여기에 **어느 쪽을 권하는 뉘앙스가 섞이면 안 된다** — 두 선택지의 프롬프트는 구조적으로 대칭이어야 한다.

---

## [1] Capture — 브라우저에서 올라오는 원자료

`POST /captures`

```ts
Capture {
  session_id: string
  segment: "neutral" | "option"      // neutral = 중립 앵커 (default 확보용)
  option_id: string | null           // segment="option"일 때만
  phase: "imagine" | "speak"

  rgb_series: RgbSample[] | null     // 레거시 서버 rPPG 입력
  rppg_measurement: RppgMeasurement | null // 새 브라우저 rPPG 요약값
  audio_base64: string | null        // phase="speak"에서 필수. ★16-bit PCM WAV
  transcript: string | null          // 브라우저 STT 결과

  fps: number                        // rgb_series 실측 프레임레이트
  duration_sec: number
}

RgbSample {
  t: number    // 시작 기준 경과 초
  r: number    // 얼굴 ROI 평균 (0~255)
  g: number
  b: number
}

RppgMeasurement {
  source: "rppg-web"
  version: string
  bpm: number
  confidence: number              // 0~1
  signal_quality: number          // 0~1
  agreement: number | null        // estimator 간 일치도
  reason_codes: string[]
  stable_sample_count: number
}
```

**프라이버시 전제** — 영상 프레임 원본은 서버로 보내지 않는다. 새 클라이언트는
브라우저의 `rppg-web`에서 처리한 **BPM과 품질 요약만** 전송한다. 기존
`rgb_series + fps`는 저장 데이터와 병렬 브랜치 호환을 위한 임시 폴백이며,
`rppg_measurement`가 있으면 서버는 이를 우선 사용한다.

**오디오 포맷** — `audio_base64`는 **16-bit PCM WAV**여야 한다. `MediaRecorder` 기본 출력(WebM/Opus)은 서버에서 ffmpeg 없이 못 읽으므로, 브라우저가 Web Audio API로 디코드한 뒤 WAV로 인코딩해서 보낸다. 서버에 미디어 코덱 의존성을 만들지 않기 위한 선택이다.

### 세션 내 Capture 구성

| segment | phase | 길이 | 용도 |
|---|---|---|---|
| `neutral` | `imagine` | 15초 | **default 심박** + rPPG 워밍업 ("화면의 점을 편하게 바라보세요") |
| `neutral` | `speak` | 15초 | **default 음성** ("오늘 아침에 뭐 하셨어요?") |
| `option`(A) | `imagine` | 15초 | 심박 ★ |
| `option`(A) | `speak` | 10초 | 음성 ★ |
| `option`(B) | `imagine` | 15초 | 심박 |
| `option`(B) | `speak` | 10초 | 음성 |

중립 앵커는 **고민과 무관한 발화**여야 한다 ("오늘 아침에 뭐 하셨어요?"). 고민을 말하는 순간 이미 긴장 상태다.

> ⚠️ **중립 앵커에도 `imagine` 구간이 필요하다.**
> 심박은 `imagine`(정지) 구간에서만 측정되므로, 중립에 `speak`만 두면 **default 심박이 없어
> 상태축에서 심박이 통째로 빠진다.** 안정 시 심박은 원래 말하는 중이 아니라 쉬는 중에 재는 것이 맞다.
> 총 세션 길이는 약 80초.

---

## [2] Features — 특징 추출

```ts
Features {
  capture_id: string
  voice: VoiceFeatures | null      // phase="speak"에서만
  hr: HeartRateFeatures | null     // phase="imagine"에서만
}

VoiceFeatures {
  f0_mean: number
  f0_std: number
  loudness_mean: number
  jitter_local: number
  shimmer_local: number
  hnr: number
  speech_rate: number
  pause_ratio: number
  egemaps: Record<string, number> | null   // eGeMAPS 88 전체 (있으면)
}

HeartRateFeatures {
  bpm: number
  confidence: number               // 0~1  ★항상 반환
  snr_db: number | null             // 레거시 서버 RGB 분석에서만
  source: "server_rgb" | "rppg-web"
  signal_quality: number | null
  agreement: number | null
  reason_codes: string[]
  hrv_rmssd: number | null         // ★MVP는 항상 null. 웨어러블 연동 시 채움
}
```

**`confidence`는 선택이 아니라 필수다.** 웹캠 rPPG는 조명·움직임에 민감하다.
`confidence < 0.4`이면 `[4]` 판정에서 **심박 축을 제외**하고 음성만으로 간다.

---

## [3] Delta — 상대화 ★가장 혼동되는 단계

**두 축은 서로 다른 질문에 답한다. 절대 섞지 말 것.**

```
Δ(A, B)            →  선호   "어느 쪽에 마음이 가 있는가"
(A,B) vs default   →  상태   "지금 이 사람은 어떤 상태에서 이 기록을 남겼는가"
```

`default`는 **선호 신호가 아니다.** 선호는 오직 A와 B의 차이에서 나온다.
`default`는 그 차이를 **어떤 조건에서 읽어야 하는지 알려주는 프레임**이다.

```ts
Delta {
  session_id: string
  baseline_source: "session_neutral" | "accumulated" | "continuous_wearable"

  preference: {                          // Δ(A, B)
    option_a_id: string
    option_b_id: string
    per_metric: Record<MetricKey, number>   // B 기준 A의 상대차. 부호 있음
  }

  state: {                               // (A,B) 평균 vs default
    per_metric: Record<MetricKey, number>
    default_available: boolean           // false면 상태 판정 unknown
  }
}
```

### `baseline_source` 교체 지점

| 값 | 의미 | 상태 |
|---|---|---|
| `session_neutral` | 세션 시작 20초 중립 앵커 | **MVP** |
| `accumulated` | 지금까지 중립 앵커들의 평균 | 세션이 쌓이면 |
| `continuous_wearable` | 웨어러블 지속 수집 | 궁극 해법 (Q4) |

`[3]` 단계만 갈아끼우면 이행 가능하도록 유지한다.

---

## [4] Verdict — 판정

```ts
Verdict {
  preference: {
    lean: "A" | "B" | "none" | "contradictory"
    lean_option_id: string | null
    magnitude: number          // 0~1
    confidence: number         // 0~1  ★state가 aroused면 낮춘다
    contributing: Record<MetricKey, number>   // 어떤 지표가 얼마나 기여했나
  }

  state: {
    label: "calm" | "aroused" | "flat" | "unknown"
    magnitude: number
  }

  order_note: string | null    // 순서 효과 고지 (Q1) — "A를 먼저 말씀하셨어요"
  excluded_metrics: MetricKey[]  // 신뢰도 미달로 제외된 지표 (예: 심박)
}
```

| `lean` | 조건 |
|---|---|
| `A` / `B` | 한쪽으로 뚜렷 |
| `none` | 차이 미미 — 진짜 팽팽하거나 아직 안 익은 고민 |
| `contradictory` | 음성과 심박이 서로 반대 방향 |

| `state.label` | 조건 |
|---|---|
| `calm` | 평소 수준 — 선호 신호 신뢰도 높음 |
| `aroused` | 전반적 각성/긴장 — 이 고민 자체가 무겁다 |
| `flat` | 평소보다 전반적으로 낮음 — 피로/무기력/체념 |
| `unknown` | `default_available: false` |

---

## [5] Report — 메타인지 리포트

`Verdict`가 LLM에 들어가지만, **LLM은 `lean`을 절대 발화하지 않는다.**

```ts
Report {
  state_note: string                // ① 상태 고지 (프레임)
  observations: string[]            // ② 관찰만. 판정·라벨·원인추정 없음
  tagging_question: string          // ③ ★비대칭 질문 — 신호가 강한 쪽으로 향한다
  tagging_option_id: string | null  //    ③이 향한 선택지. 태그 귀속에 필요
  body_tag_options: string[]        //    ["가슴 답답", "손끝 떨림", "설렘", "찜찜함", ...]
  self_statement_question: string   // ④ "지금은 어느 쪽에 마음이 더 가 있는 것 같으세요?"
}
```

### 금지 (하드 제약)

```
✗ 어느 쪽이 낫다/맞다              → 결정 대행
✗ 감정 라벨 단정 ("불안하시군요")   → 결정 대행과 동일
✗ 원인 추정 ("~때문에")
✗ 조언·제안·격려
```

**유도는 관찰이 아니라 질문에서 일어난다.** `observations`는 데이터 번역일 뿐이고,
`tagging_question`의 *방향*이 우리가 쥔 유일한 핸들이다 (비대칭 질문 원칙).

---

## [6] Annotation — 사용자 태깅

`POST /sessions/{id}/annotation`

```ts
Annotation {
  session_id: string
  option_id: string | null          // 어느 선택지에 대한 태깅인지
  body_tags: string[]
  body_tag_custom: string | null
  self_lean_option_id: string | null  // ★사용자가 자기 입으로 말한 결론
  self_lean_note: string | null
}
```

`self_lean_option_id`가 이 제품의 **핵심 산출물**이다.
우리가 판정한 `verdict.preference.lean`이 아니라, **사용자가 스스로 말한 것**이 저장되고 회고의 기준점이 된다.

---

## [7] Session — 저장 단위

```ts
Session {
  id: string
  decision_id: string
  captures: Capture[]
  features: Features[]
  delta: Delta
  verdict: Verdict          // 내부 판정 — 사용자에게 직접 노출하지 않는다
  report: Report
  annotation: Annotation | null
  created_at: datetime
}
```

---

## [8] 축적

```ts
Retrospective {
  session_id: string
  horizon: "1w" | "3m" | "6m" | "1y"
  chosen_option_id: string | null    // 실제로 무엇을 골랐나
  satisfaction: number               // 1~5
  note: string | null
  created_at: datetime
}
```

**확신(3층)의 계산**: `annotation.self_lean_option_id` == `retrospective.chosen_option_id` 인 경우들의 만족도 분포 vs 아닌 경우들의 분포.
→ "내 직관을 따랐을 때 실제로 더 만족했는가"

```ts
ValueMap {                          // 가치관 지도 (2층)
  axes: { axis: string, sessions: string[], lean_pattern: string }[]
}
```
`Decision.value_axis`를 가로질러 집계한다. 자세한 축 추출 방식은 `OPEN_QUESTIONS.md` Q5.
