/**
 * 파이프라인 계약 — backend/app/schemas 와 1:1 대응.
 *
 * 정의의 단일 진실 소스는 `docs/CONTRACTS.md`.
 * 백엔드 스키마를 고치면 이 파일도 함께 고칠 것.
 */

// ─────────────────────────────────────────────────────────── 공통

/** Delta 계산에 쓰이는 표준 지표 키. */
export type MetricKey =
  | 'f0_mean'
  | 'f0_std'
  | 'loudness_mean'
  | 'jitter_local'
  | 'shimmer_local'
  | 'hnr'
  | 'speech_rate'
  | 'pause_ratio'
  | 'bpm';

/** 지표별 상대 변화율(비율). 0.18 == 18% 높음. 절대치는 쓰지 않는다. */
export type MetricDelta = Partial<Record<MetricKey, number>>;

export interface ApiError {
  code: string;
  message: string;
}

/** 팀 컨벤션 응답 형식. */
export interface ApiResponse<T> {
  ok: boolean;
  data: T | null;
  error: ApiError | null;
}

// ─────────────────────────────────────────────────────── [0] 고민 등록

export interface Option {
  id: string;
  label: string;
  /** LLM 생성. 두 선택지의 프롬프트는 구조적으로 대칭이어야 한다. */
  imagine_prompt: string;
  speak_prompt: string;
  /** 실제 제시 순서. 순서 효과 보정을 위해 랜덤화 결과를 기록 (OPEN_QUESTIONS Q1). */
  order_index: number;
  /**
   * ★value_axis의 어느 극인가. 예: "성장".
   *
   * 라벨은 고민마다 다르므로("이직한다" / "대학원 간다") 라벨을 세면 패턴이 안 보인다.
   * 같은 극으로 모아야 [8] 가치관 지도가 "성장 4회, 안정 1회"가 된다.
   */
  axis_side: string | null;
}

export interface Decision {
  id: string;
  raw_input: string;
  title: string;
  /** LLM 추출 가치 축. 예: "안정 vs 성장". [8] 가치관 지도의 축. */
  value_axis: string;
  options: Option[];
  created_at: string;
}

// ────────────────────────────────────────────────────────── [1] 캡처

/** 중립 앵커는 고민과 무관한 발화여야 한다 — 고민을 말하는 순간 이미 긴장 상태다. */
export type Segment = 'neutral' | 'option';

/** imagine = 정지 상태에서 심박 측정, speak = 발화 음성 측정. */
export type Phase = 'imagine' | 'speak';

export interface RgbSample {
  /** 시작 기준 경과 초. */
  t: number;
  r: number;
  g: number;
  b: number;
}

/** 브라우저 안에서 rppg-web으로 계산한 요약값. 영상/RGB 원자료는 포함하지 않는다. */
export interface RppgMeasurement {
  source: 'rppg-web';
  version: string;
  bpm: number;
  confidence: number;
  signal_quality: number;
  agreement: number | null;
  reason_codes: string[];
  stable_sample_count: number;
}

/**
 * 프라이버시 전제: 영상 프레임 원본은 서버로 보내지 않는다.
 * 새 흐름은 rppg-web이 브라우저에서 계산한 심박/품질 요약만 전송한다.
 */
export interface Capture {
  id?: string;
  session_id: string;
  segment: Segment;
  option_id: string | null;
  phase: Phase;
  /** 레거시 서버 분석 경로. rppg_measurement가 없을 때만 사용한다. */
  rgb_series: RgbSample[] | null;
  /** 새 클라이언트 분석 경로. phase === 'imagine'에서 사용한다. */
  rppg_measurement: RppgMeasurement | null;
  /** phase === 'speak' 에서 필수. */
  audio_base64: string | null;
  transcript: string | null;
  /** rPPG 주파수 해석에 필요한 실측 프레임레이트. */
  fps: number;
  duration_sec: number;
}

// ─────────────────────────────────────────────────────── [2] 특징 추출

export interface VoiceFeatures {
  f0_mean: number;
  f0_std: number;
  loudness_mean: number;
  jitter_local: number;
  shimmer_local: number;
  hnr: number;
  speech_rate: number;
  pause_ratio: number;
  /** eGeMAPS 88 전체. openSMILE이 있을 때만. */
  egemaps: Record<string, number> | null;
}

export interface HeartRateFeatures {
  bpm: number;
  /** 0~1. 항상 반환된다. 0.4 미만이면 판정에서 심박 축이 제외된다. */
  confidence: number;
  snr_db: number | null;
  source: 'server_rgb' | 'rppg-web';
  signal_quality: number | null;
  agreement: number | null;
  reason_codes: string[];
  /** MVP(웹캠 rPPG)에서는 항상 null. 웨어러블 연동 시 채운다. */
  hrv_rmssd: number | null;
}

export interface Features {
  capture_id: string;
  voice: VoiceFeatures | null;
  hr: HeartRateFeatures | null;
}

export const CONFIDENCE_FLOOR = 0.4;

// ────────────────────────────────────────── [3][4] 상대화 · 판정

/**
 * ⚠️ 두 축은 서로 다른 질문에 답한다. 절대 섞지 말 것.
 *
 *   Δ(A, B)          → 선호  "어느 쪽에 마음이 가 있는가"
 *   (A,B) vs default → 상태  "어떤 상태에서 이 기록을 남겼는가"
 *
 * default는 선호 신호가 아니다. 선호는 오직 A와 B의 차이에서 나온다.
 */
export type BaselineSource =
  /** 세션 시작 20초 중립 앵커. MVP. */
  | 'session_neutral'
  /** 중립 앵커들의 누적 평균. */
  | 'accumulated'
  /** 웨어러블 지속 수집. 궁극 해법 (OPEN_QUESTIONS Q4). */
  | 'continuous_wearable';

export interface PreferenceDelta {
  option_a_id: string;
  option_b_id: string;
  /** B 대비 A의 상대차. 부호 있음. */
  per_metric: MetricDelta;
  /**
   * 잠재공간에서 A와 B의 거리 (0~2). 부호 없음.
   *
   * per_metric은 손으로 고른 8개 지표를 각각 본다. 이건 eGeMAPS 88 전부와
   * 발화 의미 벡터를 섞은 표현에서의 거리라 상호작용과 언어 축이 들어온다.
   * **크기만 나오고 방향은 안 나온다** — 방향은 라벨이 쌓여야 학습된다 (Q8).
   */
  latent_distance: number | null;
}

export interface StateDelta {
  per_metric: MetricDelta;
  /** false면 상태 판정은 'unknown'. */
  default_available: boolean;
  /** 잠재공간에서 (A,B) 평균이 default로부터 떨어진 거리 (0~2). */
  latent_distance: number | null;
}

export interface Delta {
  session_id: string;
  baseline_source: BaselineSource;
  preference: PreferenceDelta;
  state: StateDelta;
}

export type Lean =
  | 'A'
  | 'B'
  /** 차이 미미 — 진짜 팽팽하거나 아직 안 익은 고민. */
  | 'none'
  /** 음성과 심박이 서로 반대 방향. */
  | 'contradictory';

export type StateLabel =
  /** 평소 수준 — 선호 신호 신뢰도 높음. */
  | 'calm'
  /** 전반적 각성/긴장 — 이 고민 자체가 무겁다. */
  | 'aroused'
  /** 평소보다 전반적으로 낮음 — 피로/무기력/체념. */
  | 'flat'
  | 'unknown';

export interface PreferenceVerdict {
  lean: Lean;
  lean_option_id: string | null;
  magnitude: number;
  /** 상태가 'aroused'면 낮아진다. */
  confidence: number;
  contributing: MetricDelta;
}

export interface StateVerdict {
  label: StateLabel;
  magnitude: number;
}

/**
 * 내부 판정. **UI에 직접 렌더링하지 않는다.**
 * LLM 입력으로만 쓰이고, LLM은 lean을 절대 발화하지 않는다.
 */
export interface Verdict {
  session_id: string;
  preference: PreferenceVerdict;
  state: StateVerdict;
  /** 순서 효과 고지 (OPEN_QUESTIONS Q1). */
  order_note: string | null;
  excluded_metrics: MetricKey[];
}

// ─────────────────────────────────────────── [5][6] 리포트 · 태깅

/**
 * 사용자에게 보이는 유일한 산출물. 순서가 곧 설계다.
 *
 * 금지: 어느 쪽이 낫다 / 감정 라벨 단정 / 원인 추정 / 조언·격려
 */
export interface Report {
  /** ① 상태 고지. 프레임이므로 가장 먼저. */
  state_note: string;
  /** ② 관찰만. 판정·라벨·원인추정 없음. */
  observations: string[];
  /** ③ 비대칭 질문 — 신호가 강한 쪽으로 향한다. */
  tagging_question: string;
  /** ③이 어느 선택지를 향한 질문인지. 질문 문구에 이미 라벨이 드러나므로 추가 노출은 없다. */
  tagging_option_id: string | null;
  body_tag_options: string[];
  /** ④ "지금은 어느 쪽에 마음이 더 가 있는 것 같으세요?" */
  self_statement_question: string;
}

export interface Annotation {
  session_id: string;
  option_id: string | null;
  body_tags: string[];
  body_tag_custom: string | null;
  /**
   * ★핵심 산출물. 우리가 판정한 lean이 아니라 사용자가 자기 입으로 말한 것.
   * 사용자가 자기 입으로 말해야 자기 결정이 되고, 이게 회고의 기준점이 된다.
   */
  self_lean_option_id: string | null;
  self_lean_note: string | null;
}

// ──────────────────────────────────────────── [7][8] 저장 · 축적

export interface Session {
  id: string;
  decision_id: string;
  captures: Capture[];
  features: Features[];
  delta: Delta | null;
  /** 내부 판정. UI에 직접 노출하지 않는다. */
  verdict: Verdict | null;
  report: Report | null;
  annotation: Annotation | null;
  created_at: string;
}

/** 1주부터 시작한다 — 3개월을 기다리지 않고 첫 피드백 루프를 돌린다. */
export type Horizon = '1w' | '3m' | '6m' | '1y';

export interface Retrospective {
  session_id: string;
  horizon: Horizon;
  chosen_option_id: string | null;
  satisfaction: number;
  note: string | null;
  created_at: string;
}

export interface ValueAxisEntry {
  axis: string;
  session_ids: string[];
  /** 관찰만. "5번의 기록 중 — 성장 4회, 안정 1회". 규정하지 않는다. */
  lean_pattern: string;
  /** 극별 횟수. 많은 쪽부터. 예: { "성장": 5, "안정": 1 } */
  side_counts: Record<string, number>;
  /** 극을 붙이지 못해 집계에서 빠진 기록 수. 조용히 빼지 않는다. */
  unlabelled_count: number;
}

/** 가치관 지도 (2층). `GET /value-map`. 축 추출 방식은 OPEN_QUESTIONS Q5. */
export interface ValueMap {
  axes: ValueAxisEntry[];
}

export interface ConvictionGroup {
  /** 그때 자기 입으로 말한 쪽대로 골랐는가. */
  followed_intuition: boolean;
  count: number;
  average_satisfaction: number | null;
}

/**
 * 확신 (3층). `GET /conviction`.
 *
 * ★결론을 내지 않는다. 자기 진술대로 고른 경우와 아닌 경우의 만족도를 나란히 놓을
 * 뿐이고, 그 대조에서 무엇을 읽을지는 사용자가 정한다.
 * 비교 기준이 우리 판정이 아니라 `annotation.self_lean_option_id`인 이유도 같다.
 */
export interface Conviction {
  total_retrospectives: number;
  groups: ConvictionGroup[];
  /** 관찰 한 문장. 판정이 아니다. */
  note: string;
}
