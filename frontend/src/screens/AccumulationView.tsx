/**
 * [8] 축적 뷰 — 가치관(2층)과 확신(3층).
 *
 *   1회   → 선호      "고민 중인 줄 알았는데 사실 B에 마음이 가 있구나"
 *   반복  → 가치관    "나는 이런 걸 중요하게 여기는 사람이구나"    ← 여기
 *   3개월 → 확신      "내 직관은 믿을 만하구나"                  ← 여기
 *
 * 1회 세션만 보면 이 제품은 "선호 파악 도구"로만 보인다. 핵심 가치는 반복에서 나온다.
 *
 * ★이 화면은 결론을 쓰지 않는다.
 * "당신은 성장을 중시하는 사람입니다"도, "당신의 직관은 정확합니다"도 안 된다.
 * 숫자와 서버가 준 관찰 문장만 놓는다. 무엇을 읽을지는 사용자가 정한다 —
 * 그 판단 자체가 메타인지 훈련이고, 대신 해주면 실패 모드 ②를 재생산한다.
 */

import { useEffect, useState } from 'react';
import { fetchConviction, fetchValueMap } from '../api/client';
import type { Conviction, ValueMap } from '../types/contracts';

interface Props {
  onBack: () => void;
}

export function AccumulationView({ onBack }: Props) {
  const [valueMap, setValueMap] = useState<ValueMap | null>(null);
  const [conviction, setConviction] = useState<Conviction | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchValueMap(), fetchConviction()])
      .then(([map, conv]) => {
        if (cancelled) return;
        setValueMap(map);
        setConviction(conv);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : '쌓인 기록을 불러오지 못했습니다.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="panel">
        <h1 className="panel__title">쌓인 기록</h1>
        <p className="panel__lead">{error}</p>
        <button className="button" type="button" onClick={onBack}>
          돌아가기
        </button>
      </div>
    );
  }

  if (!valueMap || !conviction) {
    return (
      <div className="panel">
        <p className="panel__lead">쌓인 기록을 불러오는 중…</p>
      </div>
    );
  }

  const axes = valueMap.axes.filter((axis) => Object.keys(axis.side_counts).length > 0);

  return (
    <div className="panel">
      <h1 className="panel__title">쌓인 기록</h1>

      {/* ── 2층: 가치관 ── */}
      <section className="layer">
        <h2 className="layer__title">반복되는 축</h2>
        <p className="panel__note">
          한 번의 기록은 그날의 선호를 보여줄 뿐이에요. 같은 축이 반복될수록 무엇이
          보이는지는 직접 읽어보세요.
        </p>

        {axes.length === 0 ? (
          <p className="panel__note">
            아직 축이 반복되지 않았어요. 기록이 몇 번 더 쌓이면 여기에 나타납니다.
          </p>
        ) : (
          <ul className="axes">
            {axes.map((axis) => (
              <li key={axis.axis} className="axis">
                <div className="axis__head">
                  <span className="axis__name">{axis.axis}</span>
                  <span className="axis__count">
                    {Object.values(axis.side_counts).reduce((sum, n) => sum + n, 0)}회
                  </span>
                </div>
                <SideBar counts={axis.side_counts} />
                <p className="axis__pattern">{axis.lean_pattern}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 3층: 확신 ── */}
      <section className="layer">
        <h2 className="layer__title">그때의 마음과 지금의 만족</h2>

        {conviction.total_retrospectives === 0 ? (
          <p className="panel__note">
            회고는 기록하고 한참 뒤에 물어봐요. 1주, 3개월, 6개월 — 그때 다시 만나요.
          </p>
        ) : (
          <>
            <div className="conviction">
              {conviction.groups.map((group) => (
                <div key={String(group.followed_intuition)} className="conviction__group">
                  <span className="conviction__label">
                    {group.followed_intuition
                      ? '그때 말한 쪽으로 골랐을 때'
                      : '다른 쪽으로 골랐을 때'}
                  </span>
                  <span className="conviction__value">
                    {group.average_satisfaction === null
                      ? '기록 없음'
                      : `만족 ${group.average_satisfaction.toFixed(1)}`}
                  </span>
                  <span className="conviction__count">{group.count}건</span>
                </div>
              ))}
            </div>
            {/* 서버가 준 관찰 문장. 여기에 해석을 덧붙이지 않는다. */}
            <p className="report__state">{conviction.note}</p>
          </>
        )}
      </section>

      <button className="button" type="button" onClick={onBack}>
        돌아가기
      </button>
    </div>
  );
}

/** 극별 비율 막대. 굳어진 축과 갈리는 축이 한눈에 구별돼야 한다. */
function SideBar({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  if (total === 0) return null;

  return (
    <div className="sidebar" role="img" aria-label={entries.map(([s, n]) => `${s} ${n}회`).join(', ')}>
      {entries.map(([side, n], index) => (
        <div
          key={side}
          className={`sidebar__part sidebar__part--${index % 2 === 0 ? 'a' : 'b'}`}
          style={{ width: `${(n / total) * 100}%` }}
        >
          <span className="sidebar__text">{side}</span>
        </div>
      ))}
    </div>
  );
}
