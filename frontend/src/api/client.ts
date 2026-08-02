/**
 * 백엔드 클라이언트.
 *
 * 팀 컨벤션 응답 형식 { ok, data, error } 를 여기서 벗겨내고,
 * 실패는 예외로 올린다 — 화면 코드가 매번 ok를 검사하지 않도록.
 */

import type {
  Annotation,
  ApiResponse,
  Capture,
  Conviction,
  Decision,
  Features,
  Report,
  Retrospective,
  Session,
  ValueMap,
} from '../types/contracts';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export class ApiCallError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = 'ApiCallError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiCallError('서버에 연결할 수 없습니다.', 'network_error');
  }

  const body = (await response.json().catch(() => null)) as ApiResponse<T> | null;
  if (!body?.ok || body.data === null) {
    throw new ApiCallError(
      body?.error?.message ?? '요청을 처리하지 못했습니다.',
      body?.error?.code ?? 'unknown_error',
    );
  }
  return body.data;
}

const post = <T>(path: string, payload: unknown): Promise<T> =>
  request<T>(path, { method: 'POST', body: JSON.stringify(payload) });

/** [0] 고민 한 문장 → 선택지 2개 + 가치축 + 대칭 프롬프트. */
export const createDecision = (rawInput: string): Promise<Decision> =>
  post('/decisions', { raw_input: rawInput });

export const createSession = (decisionId: string): Promise<Session> =>
  post('/sessions', { decision_id: decisionId });

/** [1] 캡처 업로드 → [2] 특징 추출 결과가 즉시 돌아온다. */
export const uploadCapture = (sessionId: string, capture: Capture): Promise<Features> =>
  post(`/sessions/${sessionId}/captures`, capture);

/**
 * [3][4][5] 분석 → 리포트.
 *
 * 돌아오는 것은 Report 뿐이다. 내부 판정(Verdict)은 서버에 저장만 되고
 * 클라이언트로 오지 않는다 — 우리가 판정했다는 사실이 노출되면
 * 사용자는 다시 결정을 아웃소싱하게 된다.
 */
export const analyzeSession = (sessionId: string): Promise<Report> =>
  post(`/sessions/${sessionId}/analyze`, {});

/** [6] 사용자 태깅. self_lean_option_id 가 이 제품의 핵심 산출물. */
export const saveAnnotation = (
  sessionId: string,
  annotation: Annotation,
): Promise<Annotation> => post(`/sessions/${sessionId}/annotation`, annotation);

export const saveRetrospective = (
  sessionId: string,
  retrospective: Retrospective,
): Promise<Retrospective> =>
  post(`/sessions/${sessionId}/retrospective`, retrospective);

/** [8] 2층 — 고민들을 가로질러 반복되는 축. */
export const fetchValueMap = (): Promise<ValueMap> => request('/value-map');

/** [8] 3층 — 그때 자기 입으로 말한 것과 지금의 만족도를 대조한다. */
export const fetchConviction = (): Promise<Conviction> => request('/conviction');
