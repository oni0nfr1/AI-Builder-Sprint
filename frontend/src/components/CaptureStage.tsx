/**
 * 캡처 진행 표시 — 안내 문구, 남은 시간, 신호 품질.
 *
 * 영상 요소는 여기 두지 않는다. 스텝이 바뀔 때마다 <video>가 언마운트되면
 * srcObject 연결이 끊기므로, App이 트리의 고정된 자리에서 소유한다.
 */

import type { RoiQuality } from '../lib/faceRoi';
import type { CaptureStep } from '../lib/sessionFlow';

interface Props {
  step: CaptureStep;
  stepIndex: number;
  stepCount: number;
  elapsedSec: number;
  quality: RoiQuality;
}

const TOO_DARK = 60;
const TOO_BRIGHT = 235;

/** 발화 구간에서는 심박을 재지 않으므로 조명 안내를 띄우지 않는다. */
function qualityHint(step: CaptureStep, quality: RoiQuality): string | null {
  if (step.phase !== 'imagine') return null;
  if (!quality.faceDetected) return '얼굴이 화면 안에 들어오도록 맞춰주세요.';
  if (quality.brightness < TOO_DARK) return '조금 더 밝은 곳이면 신호가 잘 잡혀요.';
  if (quality.brightness > TOO_BRIGHT) return '빛이 너무 강해요. 조명을 조금 낮춰주세요.';
  return null;
}

export function CaptureStage({ step, stepIndex, stepCount, elapsedSec, quality }: Props) {
  const remaining = Math.max(0, Math.ceil(step.durationSec - elapsedSec));
  const progress = Math.min(1, elapsedSec / step.durationSec);
  const hint = qualityHint(step, quality);

  return (
    <div className="stage">
      <div className="stage__meta">
        <span>
          {stepIndex + 1} / {stepCount} · {step.stepLabel}
        </span>
        <span className="stage__phase">
          {step.phase === 'imagine' ? '상상하는 중' : '말하는 중'}
        </span>
      </div>

      <p className="stage__instruction">{step.instruction}</p>

      <div
        className="stage__progress"
        role="progressbar"
        aria-valuenow={Math.round(progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="stage__progress-fill" style={{ width: `${progress * 100}%` }} />
      </div>
      <p className="stage__remaining">{remaining}초</p>

      {hint && <p className="stage__hint">{hint}</p>}
    </div>
  );
}
