/**
 * [5] 리포트 + [6] 태깅.
 *
 * 순서가 곧 설계다:
 *   ① 상태 고지 — 이 기록을 어떤 조건에서 남겼는지. 프레임이므로 가장 먼저.
 *   ② 관찰      — 측정된 차이. 판정·라벨·원인추정 없음.
 *   ③ 신체 태깅 — 해석의 주체는 사용자다.
 *   ④ 자기 진술 — ★사용자가 자기 입으로 결론을 말한다.
 *
 * ④를 별도 단계로 둔 이유: 자기 입으로 말해야 우리 결정이 아니라 자기 결정이 되고,
 * 이 진술이 나중에 회고의 기준점이 된다.
 *
 * 이 화면은 Report의 필드만 렌더링한다. 내부 판정(Verdict)은 애초에 서버에서 오지 않는다.
 */

import { useState } from 'react';
import type { Annotation, Decision, Report } from '../types/contracts';

interface Props {
  report: Report;
  decision: Decision;
  onSubmit: (annotation: Omit<Annotation, 'session_id'>) => void;
  submitting?: boolean;
}

export function ReportView({ report, decision, onSubmit, submitting }: Props) {
  const [stage, setStage] = useState<'observe' | 'commit'>('observe');
  const [bodyTags, setBodyTags] = useState<string[]>([]);
  const [customTag, setCustomTag] = useState('');
  const [selfLean, setSelfLean] = useState<string | null>(null);
  const [selfNote, setSelfNote] = useState('');

  const toggleTag = (tag: string) =>
    setBodyTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );

  if (stage === 'observe') {
    return (
      <div className="panel">
        {/* ① 상태 고지 — 이번 기록을 얼마나 믿을지 사용자가 스스로 판단하게 한다 */}
        <p className="report__state">{report.state_note}</p>

        {/* ② 관찰 */}
        <ul className="report__observations">
          {report.observations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>

        {/* ③ 신체 태깅 */}
        <h2 className="report__question">{report.tagging_question}</h2>
        <div className="tags">
          {report.body_tag_options.map((tag) => (
            <button
              key={tag}
              type="button"
              className={`tag ${bodyTags.includes(tag) ? 'tag--on' : ''}`}
              onClick={() => toggleTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
        <input
          className="panel__input"
          value={customTag}
          onChange={(event) => setCustomTag(event.target.value)}
          placeholder="다른 느낌이 있었다면 적어주세요"
        />

        <button className="button" type="button" onClick={() => setStage('commit')}>
          다음
        </button>
      </div>
    );
  }

  return (
    <div className="panel">
      {/* ④ 자기 진술 — 결론은 사용자가 낸다 */}
      <h2 className="report__question">{report.self_statement_question}</h2>

      <div className="choices">
        {decision.options.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`choice ${selfLean === option.id ? 'choice--on' : ''}`}
            onClick={() => setSelfLean(option.id)}
          >
            {option.label}
          </button>
        ))}
        <button
          type="button"
          className={`choice ${selfLean === '' ? 'choice--on' : ''}`}
          onClick={() => setSelfLean('')}
        >
          아직 모르겠어요
        </button>
      </div>

      <textarea
        className="panel__input"
        value={selfNote}
        onChange={(event) => setSelfNote(event.target.value)}
        placeholder="그렇게 느낀 이유가 떠오르면 적어주세요 (선택)"
        rows={3}
      />

      <button
        className="button"
        type="button"
        disabled={selfLean === null || submitting}
        onClick={() =>
          onSubmit({
            option_id: report.tagging_option_id,
            body_tags: bodyTags,
            body_tag_custom: customTag.trim() || null,
            self_lean_option_id: selfLean || null,
            self_lean_note: selfNote.trim() || null,
          })
        }
      >
        {submitting ? '저장하는 중…' : '기록 마치기'}
      </button>

      <button className="button button--ghost" type="button" onClick={() => setStage('observe')}>
        관찰 다시 보기
      </button>
    </div>
  );
}
