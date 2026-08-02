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
import { RoiSampler, recordRgbSeries, type RoiQuality } from '../lib/faceRoi';
import { buildSteps, type CaptureStep } from '../lib/sessionFlow';
import { Transcriber } from '../lib/stt';
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
  quality: RoiQuality;
  report: Report | null;
  errorMessage: string | null;
}

const IDLE_QUALITY: RoiQuality = { brightness: 0, faceDetected: false };

const INITIAL: FlowState = {
  phase: 'input',
  decision: null,
  steps: [],
  stepIndex: 0,
  elapsedSec: 0,
  quality: IDLE_QUALITY,
  report: null,
  errorMessage: null,
};

export function useSessionFlow(videoRef: React.RefObject<HTMLVideoElement>) {
  const [state, setState] = useState<FlowState>(INITIAL);

  const streamRef = useRef<MediaStream | null>(null);
  const samplerRef = useRef<RoiSampler | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const preflightRef = useRef<number | null>(null);

  const fail = useCallback((message: string) => {
    setState((prev) => ({ ...prev, phase: 'error', errorMessage: message }));
  }, []);

  const stopPreflight = useCallback(() => {
    if (preflightRef.current === null) return;
    window.clearInterval(preflightRef.current);
    preflightRef.current = null;
  }, []);

  /**
   * 준비 화면에서 ROI 신호를 미리 보여준다.
   *
   * 조명 경고를 캡처 중에만 띄우면 이미 15초가 흐른 뒤라 늦다. 어두운 채로
   * 세션을 끝내면 심박이 통째로 버려지므로(실측 confidence 0.05), 시작 전에
   * 사용자가 조명을 고칠 기회를 준다.
   */
  const startPreflight = useCallback(() => {
    stopPreflight();
    preflightRef.current = window.setInterval(() => {
      const sampler = samplerRef.current;
      if (!sampler) return;
      sampler.sample(performance.now());
      setState((prev) => ({ ...prev, quality: sampler.quality }));
    }, 200);
  }, [stopPreflight]);

  const stopMedia = useCallback(() => {
    stopPreflight();
    samplerRef.current?.dispose();
    samplerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, [stopPreflight]);

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

        samplerRef.current = await RoiSampler.create(video);

        setState((prev) => ({
          ...prev,
          phase: 'ready',
          decision,
          steps: buildSteps(decision),
        }));
        startPreflight();
      } catch (error) {
        stopMedia();
        fail(
          error instanceof Error
            ? `${error.message} — 카메라·마이크 권한을 허용했는지 확인해주세요.`
            : '준비 중 문제가 생겼습니다.',
        );
      }
    },
    [fail, startPreflight, stopMedia, videoRef],
  );

  /** [1] 한 스텝 캡처 → [2] 업로드. */
  const runStep = useCallback(async (step: CaptureStep) => {
    const sessionId = sessionIdRef.current;
    const sampler = samplerRef.current;
    const stream = streamRef.current;
    if (!sessionId || !sampler || !stream) throw new Error('세션이 준비되지 않았습니다.');

    if (step.phase === 'imagine') {
      // 정지 구간 — 심박만 잰다. 말하면 얼굴 근육이 움직여 rPPG가 깨진다.
      const recording = await recordRgbSeries(sampler, step.durationSec, (elapsedSec, quality) =>
        setState((prev) => ({ ...prev, elapsedSec, quality })),
      );
      await uploadCapture(sessionId, {
        session_id: sessionId,
        segment: step.segment,
        option_id: step.optionId,
        phase: 'imagine',
        rgb_series: recording.series,
        audio_base64: null,
        transcript: null,
        fps: recording.fps,
        duration_sec: recording.durationSec,
      });
      return;
    }

    // 발화 구간 — 음성만 잰다. ROI 품질은 여기서 갱신하지 않는다(측정하지 않으므로).
    const recorder = new AudioRecorder(stream);
    const transcriber = new Transcriber();
    await recorder.start();
    transcriber.start();

    await countdown(step.durationSec, (elapsedSec) =>
      setState((prev) => ({ ...prev, elapsedSec })),
    );

    const audioBase64 = await recorder.stop();
    const transcript = await transcriber.stop();
    if (!transcript && transcriber.lastError) {
      // 인식 실패는 치명적이지 않다(판정은 음향 특징에서 나온다). 다만 왜 비었는지는 남긴다.
      console.warn(`STT 결과 없음 — ${transcriber.lastError}`);
    }

    await uploadCapture(sessionId, {
      session_id: sessionId,
      segment: step.segment,
      option_id: step.optionId,
      phase: 'speak',
      rgb_series: null,
      audio_base64: audioBase64,
      transcript,
      fps: 0,
      duration_sec: step.durationSec,
    });
  }, []);

  /** 준비된 스텝들을 순서대로 돌리고 [3][4][5] 분석까지 간다. */
  const runAll = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    const steps = state.steps;
    if (!sessionId || steps.length === 0) return;

    // 캡처 루프가 직접 샘플링하므로 프리플라이트와 겹치면 안 된다.
    stopPreflight();

    try {
      for (let index = 0; index < steps.length; index += 1) {
        setState((prev) => ({
          ...prev,
          phase: 'capturing',
          stepIndex: index,
          elapsedSec: 0,
          quality: IDLE_QUALITY,
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
  }, [fail, runStep, state.steps, stopMedia, stopPreflight]);

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
