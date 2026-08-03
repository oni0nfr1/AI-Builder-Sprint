/**
 * 세션 흐름 정의 (약 80초).
 *
 *   [중립 앵커]  15초  "화면의 점을 편하게 바라보세요"   → default 심박 + rPPG 워밍업
 *                15초  "오늘 아침에 뭐 하셨어요?"        → default 음성
 *   [선택지 ①]  15초  상상 (정지)                       → 심박
 *                10초  발화                              → 음성
 *   [선택지 ②]  동일                                     ※ 제시 순서는 서버가 랜덤화
 *
 * 중립에도 imagine 구간이 있어야 한다. 심박은 정지 구간에서만 측정되므로,
 * 중립에 발화만 두면 default 심박이 없어 상태축에서 심박이 통째로 빠진다.
 *
 * 중립 앵커는 고민과 무관한 발화여야 한다 — 고민을 말하는 순간 이미 긴장 상태다.
 */

import type { Decision, Phase, Segment } from '../types/contracts';

export const NEUTRAL_IMAGINE_SEC = 15;
export const NEUTRAL_SPEAK_SEC = 15;
export const OPTION_IMAGINE_SEC = 15;
export const OPTION_SPEAK_SEC = 10;

export interface CaptureStep {
  segment: Segment;
  optionId: string | null;
  phase: Phase;
  durationSec: number;
  /** 화면에 띄울 안내 문구. */
  instruction: string;
  /** 진행 표시용 짧은 라벨. */
  stepLabel: string;
}

export function buildSteps(decision: Decision): CaptureStep[] {
  // options 배열의 순서는 A/B 정체성이고, 제시 순서는 order_index다.
  // 뒤에 말한 쪽이 자연 안정화로 차분해 보이는 편향을 줄이기 위해 서버가 랜덤화한다.
  const presented = [...decision.options].sort((a, b) => a.order_index - b.order_index);

  return [
    {
      segment: 'neutral',
      optionId: null,
      phase: 'imagine',
      durationSec: NEUTRAL_IMAGINE_SEC,
      instruction: '화면 가운데 점을 편하게 바라보세요.',
      stepLabel: '준비',
    },
    {
      segment: 'neutral',
      optionId: null,
      phase: 'speak',
      durationSec: NEUTRAL_SPEAK_SEC,
      instruction: '오늘 아침에 뭐 하셨는지 편하게 말씀해주세요.',
      stepLabel: '준비',
    },
    ...presented.flatMap((option): CaptureStep[] => [
      {
        segment: 'option',
        optionId: option.id,
        phase: 'imagine',
        durationSec: OPTION_IMAGINE_SEC,
        instruction: option.imagine_prompt,
        stepLabel: option.label,
      },
      {
        segment: 'option',
        optionId: option.id,
        phase: 'speak',
        durationSec: OPTION_SPEAK_SEC,
        instruction: option.speak_prompt,
        stepLabel: option.label,
      },
    ]),
  ];
}

export const totalDurationSec = (steps: CaptureStep[]): number =>
  steps.reduce((sum, step) => sum + step.durationSec, 0);
