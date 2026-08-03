/**
 * 세션 진행 상태 머신.
 *
 * 고민 입력 → 캡처 스텝들을 순서대로 실행 → 분석 → 리포트 → 태깅.
 * 각 스텝이 끝나는 즉시 업로드하므로, 마지막에 몰아서 기다리는 구간이 없다.
 */

import { useCallback, useRef, useState } from 'react';
import {
  analyzeSession,
  createDecision,
  createSession,
  saveAnnotation,
  uploadCapture,
} from '../api/client';
import { AudioRecorder, requestMedia } from '../lib/audio';
import {
  RoiSampler,
  describeQuality,
  lockCameraSettings,
  recordRgbSeries,
} from '../lib/faceRoi';
import {
  IDLE_RPPG_QUALITY,
  RppgController,
  UNAVAILABLE_RPPG_QUALITY,
  type RppgQuality,
} from '../lib/rppg';
import { buildSteps, type CaptureStep } from '../lib/sessionFlow';
import type { Annotation, Decision, Report } from '../types/contracts';

export type FlowPhase =
  | 'input'
  | 'preparing'
  | 'ready'
  | 'capturing'
  | 'analyzing'
  | 'report'
  | 'done'
  | 'error';

export interface FlowState {
  phase: FlowPhase;
  decision: Decision | null;
  steps: CaptureStep[];
  stepIndex: number;
  elapsedSec: number;
  quality: RppgQuality;
  report: Report | null;
  errorMessage: string | null;
}

/**
 * 브라우저 rPPG 를 못 쓸 때 우리 서버 경로가 내놓는 품질을 같은 모양으로 옮긴다.
 * 화면은 어느 경로로 쟀는지 알 필요가 없다.
 */
function toRppgQuality(sampler: RoiSampler): RppgQuality {
  const verdict = describeQuality(sampler.quality);
  return {
    available: true,
    ready: verdict.ok,
    confidence: 0,
    signalQuality: 0,
    message: verdict.message,
  };
}


const INITIAL: FlowState = {
  phase: 'input',
  decision: null,
  steps: [],
  stepIndex: 0,
  elapsedSec: 0,
  quality: IDLE_RPPG_QUALITY,
  report: null,
  errorMessage: null,
};

export function useSessionFlow(videoRef: React.RefObject<HTMLVideoElement>) {
  const [state, setState] = useState<FlowState>(INITIAL);

  const streamRef = useRef<MediaStream | null>(null);
  const rppgRef = useRef<RppgController | null>(null);
  /** 브라우저 rPPG 를 못 쓸 때만 만든다 — 서버측 경로의 입력을 모은다. */
  const samplerRef = useRef<RoiSampler | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const fail = useCallback((message: string) => {
    setState((prev) => ({ ...prev, phase: 'error', errorMessage: message }));
  }, []);

  const stopMedia = useCallback(() => {
    const rppg = rppgRef.current;
    rppgRef.current = null;
    void rppg?.dispose().catch((error: unknown) => {
      console.warn('rPPG 리소스를 정리하지 못했습니다.', error);
    });
    samplerRef.current?.dispose();
    samplerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  /** [0] 고민 등록 + 카메라·마이크 준비. */
  const start = useCallback(
    async (rawInput: string) => {
      setState({ ...INITIAL, phase: 'preparing' });
      try {
        const decision = await createDecision(rawInput);
        const session = await createSession(decision.id);
        sessionIdRef.current = session.id;

        const stream = await requestMedia();
        streamRef.current = stream;

        const video = videoRef.current;
        if (!video) throw new Error('영상 요소를 찾을 수 없습니다.');
        video.srcObject = stream;
        await video.play();

        try {
          rppgRef.current = await RppgController.create(
            video,
            (quality) => setState((prev) => ({ ...prev, quality })),
            () => {
              const failedRppg = rppgRef.current;
              rppgRef.current = null;
              void failedRppg?.dispose().catch((disposeError: unknown) => {
                console.warn('실패한 rPPG 세션을 정리하지 못했습니다.', disposeError);
              });
            },
          );
        } catch (error) {
          /*
           * 심박은 보조 신호다. 초기화 실패가 음성 기반 세션 전체를 막아서는 안 된다.
           * 다만 심박을 통째로 포기하지는 않는다 — 서버측 rPPG(ROI RGB 시계열)로
           * 물러선다. 백엔드가 두 입력을 모두 받으므로 계약은 그대로다.
           */
          console.warn('rppg-web 초기화 실패 — 서버측 rPPG 로 물러섭니다.', error);
          try {
            samplerRef.current = await RoiSampler.create(video);
          } catch (fallbackError) {
            console.warn('서버측 rPPG 도 준비하지 못했습니다.', fallbackError);
            setState((prev) => ({ ...prev, quality: UNAVAILABLE_RPPG_QUALITY }));
          }
        }

        // 자동 노출·화이트밸런스를 잠근다 — 켜져 있으면 카메라가 맥동을 상쇄한다.
        // 프리플라이트 전에 걸어야 사용자가 잠긴 상태의 밝기를 보고 조명을 맞춘다.
        const locked = await lockCameraSettings(stream);
        console.info(
          locked.length
            ? `카메라 자동보정 잠금: ${locked.join(', ')}`
            : '카메라 자동보정 잠금을 지원하지 않는 기기입니다 — 조명을 일정하게 유지해주세요.',
        );

        setState((prev) => ({
          ...prev,
          phase: 'ready',
          decision,
          steps: buildSteps(decision),
        }));
      } catch (error) {
        stopMedia();
        fail(
          error instanceof Error
            ? `${error.message} — 카메라·마이크 권한을 허용했는지 확인해주세요.`
            : '준비 중 문제가 생겼습니다.',
        );
      }
    },
    [fail, stopMedia, videoRef],
  );

  /** [1] 한 스텝 캡처 → [2] 업로드. */
  const runStep = useCallback(async (step: CaptureStep) => {
    const sessionId = sessionIdRef.current;
    const stream = streamRef.current;
    if (!sessionId || !stream) throw new Error('세션이 준비되지 않았습니다.');

    if (step.phase === 'imagine') {
      // 정지 구간 — 심박만 잰다. 말하면 얼굴 근육이 움직여 rPPG가 깨진다.
      const rppg = rppgRef.current;
      const sampler = samplerRef.current;

      if (rppg) {
        const measurement = await rppg.record(step.durationSec, (elapsedSec) =>
          setState((prev) => ({ ...prev, elapsedSec })),
        );
        await uploadCapture(sessionId, {
          session_id: sessionId,
          segment: step.segment,
          option_id: step.optionId,
          phase: 'imagine',
          rgb_series: null,
          rppg_measurement: measurement,
          audio_base64: null,
          transcript: null,
          fps: 0,
          duration_sec: step.durationSec,
        });
        return;
      }

      // 폴백 — 얼굴 ROI 의 평균 RGB 숫자만 보낸다. 영상은 여전히 브라우저를 안 떠난다.
      const recording = sampler
        ? await recordRgbSeries(sampler, step.durationSec, (elapsedSec) =>
            setState((prev) => ({ ...prev, elapsedSec, quality: toRppgQuality(sampler) })),
          )
        : null;
      if (!recording) {
        await countdown(step.durationSec, (elapsedSec) =>
          setState((prev) => ({ ...prev, elapsedSec })),
        );
      }
      await uploadCapture(sessionId, {
        session_id: sessionId,
        segment: step.segment,
        option_id: step.optionId,
        phase: 'imagine',
        rgb_series: recording?.series ?? null,
        rppg_measurement: null,
        audio_base64: null,
        transcript: null,
        fps: recording?.fps ?? 0,
        duration_sec: recording?.durationSec ?? step.durationSec,
      });
      return;
    }

    // 발화 구간 — 음성만 잰다. ROI 품질은 여기서 갱신하지 않는다(측정하지 않으므로).
    const recorder = new AudioRecorder(stream);
    await recorder.start();

    await countdown(step.durationSec, (elapsedSec) =>
      setState((prev) => ({ ...prev, elapsedSec })),
    );

    const audioBase64 = await recorder.stop();

    await uploadCapture(sessionId, {
      session_id: sessionId,
      segment: step.segment,
      option_id: step.optionId,
      phase: 'speak',
      rgb_series: null,
      rppg_measurement: null,
      audio_base64: audioBase64,
      /*
       * ★브라우저에서 인식하지 않는다. 서버가 [5] 직전에 채운다.
       *
       * Web Speech API 를 쓰다 걷어냈다. 브라우저 API 라서 로컬에서 처리할 거라
       * 가정했는데, Chrome 은 오디오를 구글 서버로 보내 인식한다. 영상 원본을
       * 서버에 안 보내려고 공들여놓고 음성은 밝히지도 않은 채 제3자에게
       * 보내고 있었다 (OPEN_QUESTIONS Q7).
       */
      transcript: null,
      fps: 0,
      duration_sec: step.durationSec,
    });
  }, []);

  /** 준비된 스텝들을 순서대로 돌리고 [3][4][5] 분석까지 간다. */
  const runAll = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    const steps = state.steps;
    if (!sessionId || steps.length === 0) return;

    try {
      for (let index = 0; index < steps.length; index += 1) {
        setState((prev) => ({
          ...prev,
          phase: 'capturing',
          stepIndex: index,
          elapsedSec: 0,
        }));
        await runStep(steps[index]);
      }

      setState((prev) => ({ ...prev, phase: 'analyzing' }));
      const report = await analyzeSession(sessionId);

      stopMedia();
      setState((prev) => ({ ...prev, phase: 'report', report }));
    } catch (error) {
      stopMedia();
      fail(error instanceof Error ? error.message : '기록 중 문제가 생겼습니다.');
    }
  }, [fail, runStep, state.steps, stopMedia]);

  /** [6] 사용자 태깅 — 해석의 주체는 사용자다. */
  const submitAnnotation = useCallback(
    async (annotation: Omit<Annotation, 'session_id'>) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId) return;
      try {
        await saveAnnotation(sessionId, { ...annotation, session_id: sessionId });
        setState((prev) => ({ ...prev, phase: 'done' }));
      } catch (error) {
        fail(error instanceof Error ? error.message : '저장하지 못했습니다.');
      }
    },
    [fail],
  );

  const reset = useCallback(() => {
    stopMedia();
    sessionIdRef.current = null;
    setState(INITIAL);
  }, [stopMedia]);

  return { state, start, runAll, submitAnnotation, reset, stopMedia };
}

/** 경과 시간을 알리며 지정 시간만큼 기다린다. */
function countdown(
  durationSec: number,
  onTick: (elapsedSec: number) => void,
): Promise<void> {
  return new Promise((resolve) => {
    const startMs = performance.now();
    const timer = window.setInterval(() => {
      const elapsedSec = (performance.now() - startMs) / 1000;
      if (elapsedSec >= durationSec) {
        window.clearInterval(timer);
        resolve();
        return;
      }
      onTick(elapsedSec);
    }, 100);
  });
}
