/**
 * 사용자 식별.
 *
 * 계정을 만들라고 하는 순간 사람은 진짜 고민을 말하지 않는다. 우리가 다루는 건
 * 몸이 흘리는 신호이고, 그 신뢰가 없으면 제품이 성립하지 않는다.
 * 그래서 로그인 없이 브라우저가 만든 UUID 하나로 간다.
 *
 * ★이게 없으면 [8] 축적이 **남의 기록을 내 것처럼** 집계하고,
 * 개인별 표준화(라벨 없는 개인화)도 성립하지 않는다.
 *
 * 한계는 분명하다 — 브라우저를 바꾸거나 저장소를 비우면 다른 사람이 된다.
 * 기기를 넘나드는 이력이 필요해지면 그때 계정을 붙인다.
 */

const STORAGE_KEY = 'intuition-note.user-id';

/** 백엔드 `app/core/identity.py` 의 검증 정규식과 맞춘다. */
function generate(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '');
  }
  // 구형 브라우저 폴백. 충돌 위험은 있지만 없는 것보다 낫다.
  return `u${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

let cached: string | null = null;

/**
 * `?user=demo` 로 열면 그 식별자로 전환한다.
 *
 * 시연용이다. 축적 뷰(2층 가치관 / 3층 확신)는 **여러 달치 이력이 있어야** 뜻이
 * 생기는데, 시연 자리에서 그걸 만들 수는 없다. 미리 심어둔 `demo` 사용자로
 * 갈아타면 바로 보여줄 수 있다 (`backend/scripts/seed_history.py`).
 *
 * ⚠️ 심어둔 이력은 **실제 측정이 아니다.** 시연에서 반드시 밝힐 것.
 */
function overrideFromUrl(): string | null {
  try {
    const requested = new URLSearchParams(window.location.search).get('user');
    return requested && _ALLOWED.test(requested) ? requested : null;
  } catch {
    return null;
  }
}

/** 백엔드 `app/core/identity.py` 와 같은 형식만 받는다. */
const _ALLOWED = /^[A-Za-z0-9_-]{8,64}$/;

export function currentUserId(): string {
  if (cached) return cached;

  const override = overrideFromUrl();
  if (override) {
    cached = override;
    try {
      window.localStorage.setItem(STORAGE_KEY, override);
    } catch {
      // 저장 못 해도 이번 세션 동안은 유지된다.
    }
    return override;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      cached = stored;
      return stored;
    }
    const created = generate();
    window.localStorage.setItem(STORAGE_KEY, created);
    cached = created;
    return created;
  } catch {
    // 시크릿 모드 등에서 localStorage 가 막힌다. 세션 동안만 유지되는 값으로 간다.
    cached = cached ?? generate();
    return cached;
  }
}
