import {
  createRppgSession,
  RppgAppMonitor,
  type RppgAppSnapshot,
  type RppgSession,
} from '@elata-biosciences/rppg-web';
import rppgWasmJsUrl from '@elata-biosciences/rppg-web/pkg/rppg_wasm.js?url';
import rppgWasmBinaryUrl from '@elata-biosciences/rppg-web/pkg/rppg_wasm_bg.wasm?url';
import type { RppgMeasurement } from '../types/contracts';

export interface RppgQuality {
  available: boolean;
  ready: boolean;
  confidence: number;
  signalQuality: number;
  message: string;
}

export const IDLE_RPPG_QUALITY: RppgQuality = {
  available: true,
  ready: false,
  confidence: 0,
  signalQuality: 0,
  message: '맥박 신호를 준비하고 있어요.',
};

export const UNAVAILABLE_RPPG_QUALITY: RppgQuality = {
  available: false,
  ready: false,
  confidence: 0,
  signalQuality: 0,
  message: '심박 측정을 사용할 수 없어 음성 신호만 기록해요.',
};

const SDK_VERSION = '0.14.0';
const AGGREGATION_WINDOW_SEC = 3;

const GUIDANCE_MESSAGES: Record<string, string> = {
  idle: '맥박 신호를 준비하고 있어요.',
  starting: '얼굴과 맥박 신호를 찾고 있어요.',
  retrying: '심박 분석을 다시 준비하고 있어요.',
  stopped: '심박 측정이 멈췄어요.',
  no_face: '화면 중앙에 얼굴 전체가 보이게 해주세요.',
  move_closer: '카메라에 조금 더 가까이 와주세요.',
  move_back: '카메라에서 조금 더 멀리 앉아주세요.',
  center_face: '얼굴을 화면 중앙으로 옮겨주세요.',
  face_too_high: '얼굴을 조금 아래로 내려주세요.',
  face_too_low: '얼굴을 조금 위로 올려주세요.',
  increase_lighting: '얼굴 앞쪽을 조금 더 밝게 해주세요.',
  finding_pulse: '맥박 신호를 찾는 중이에요. 잠시 움직이지 마세요.',
  calibrating: '신호를 확인하고 있어요. 조금만 더 기다려주세요.',
  active_monitoring: '안정적인 심박 신호를 측정하고 있어요.',
  motion_hold: '움직임이 감지됐어요. 잠시 가만히 있어주세요.',
  backend_unavailable: '브라우저 심박 분석 엔진을 불러오지 못했어요.',
  face_tracking_init_failed: '얼굴 추적 없이 화면 중앙에서 측정하고 있어요.',
  camera_not_playing: '카메라 영상을 읽지 못했어요.',
  capture_failed: '카메라 프레임을 읽지 못했어요.',
  processor_failed: '심박 신호 분석이 중단됐어요.',
  wasm_init_failed: '브라우저 심박 분석 엔진을 시작하지 못했어요.',
};

export class RppgController {
  private readonly unsubscribe: () => void;
  private operational = true;
  private disposed = false;

  private constructor(
    private readonly session: RppgSession,
    private readonly monitor: RppgAppMonitor,
    onQuality: (quality: RppgQuality) => void,
    onUnavailable: () => void,
  ) {
    this.unsubscribe = monitor.subscribe((snapshot) => {
      onQuality(toQuality(snapshot));
      if (!isOperational(snapshot)) {
        this.operational = false;
        // 실패 상태는 SDK에 남아 ready로 돌아오지 않는다. 불필요한 polling을
        // 멈추고 상위 흐름이 이 controller를 폐기하도록 알린다.
        this.monitor.stop();
        onUnavailable();
      }
    });
    monitor.start();
    onQuality(toQuality(monitor.getSnapshot()));
  }

  static async create(
    video: HTMLVideoElement,
    onQuality: (quality: RppgQuality) => void,
    onUnavailable: () => void,
  ): Promise<RppgController> {
    let session: RppgSession | null = null;
    let monitor: RppgAppMonitor | null = null;
    try {
      session = await createSdkSession(video, 'auto');

      if (session.lastError?.code === 'face_mesh_init_failed') {
        // auto fallback 세션은 오류가 남아 AppAdapter가 계속 degraded 상태가 되고
        // canPublish가 열리지 않는다. 오류 없는 video-frame 세션으로 다시 만든다.
        console.warn('FaceMesh 초기화 실패 — 중앙 프레임 모드로 다시 시작합니다.');
        await session.dispose();
        session = null;
        session = await createSdkSession(video, 'off');
      }

      if (!session.getDiagnostics().estimationAvailable) {
        throw new Error('rPPG estimation backend is unavailable.');
      }

      monitor = new RppgAppMonitor(
        session,
        {
          intervalMs: 300,
          emitImmediately: false,
          affect: false,
          maxTracePoints: 180,
          gating: { minConfidenceForStable: 0.5, stableDisplayHoldMs: 2500 },
        },
        {
          // Firefox를 포함해 Web IDL의 this 검사를 통과하도록 Window에 바인딩한다.
          setIntervalFn: window.setInterval.bind(window),
          clearIntervalFn: window.clearInterval.bind(window),
        },
      );
      return new RppgController(session, monitor, onQuality, onUnavailable);
    } catch (error) {
      monitor?.dispose();
      await session?.dispose().catch((disposeError: unknown) => {
        console.warn('초기화에 실패한 rPPG 세션을 정리하지 못했습니다.', disposeError);
      });
      throw error;
    }
  }

  record(
    durationSec: number,
    onTick: (elapsedSec: number) => void,
  ): Promise<RppgMeasurement | null> {
    const startedAt = performance.now();
    const samples: RppgAppSnapshot[] = [];

    return new Promise((resolve) => {
      const unsubscribe = this.monitor.subscribe((snapshot) => {
        const elapsedSec = (performance.now() - startedAt) / 1000;
        const bpm = snapshot.publishBpm;
        if (
          elapsedSec >= durationSec - AGGREGATION_WINDOW_SEC &&
          snapshot.canPublish &&
          bpm !== null &&
          Number.isFinite(bpm)
        ) {
          samples.push(snapshot);
        }
      });

      const timer = window.setInterval(() => {
        const elapsedSec = (performance.now() - startedAt) / 1000;
        if (elapsedSec >= durationSec) {
          window.clearInterval(timer);
          unsubscribe();
          resolve(this.operational ? summarize(samples) : null);
          return;
        }
        onTick(elapsedSec);
      }, 100);
    });
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.operational = false;
    this.unsubscribe();
    this.monitor.dispose();
    await this.session.dispose();
  }
}

function toQuality(snapshot: RppgAppSnapshot): RppgQuality {
  const operational = isOperational(snapshot);
  return {
    available: operational,
    ready: snapshot.ready,
    // 실패 직전의 metrics가 SDK snapshot에 남아 있어도 현재 품질처럼 보이지 않게 한다.
    confidence: operational ? clamp(snapshot.metrics.confidence) : 0,
    signalQuality: operational ? clamp(snapshot.metrics.signal_quality) : 0,
    message: GUIDANCE_MESSAGES[snapshot.guidance.code] ?? snapshot.message,
  };
}

function isOperational(snapshot: RppgAppSnapshot): boolean {
  return (
    snapshot.debug.estimationAvailable &&
    snapshot.status !== 'failed' &&
    snapshot.status !== 'degraded' &&
    snapshot.status !== 'stopped'
  );
}

function createSdkSession(
  video: HTMLVideoElement,
  faceMesh: 'auto' | 'off',
): Promise<RppgSession> {
  return createRppgSession({
    video,
    sampleRate: 30,
    windowSec: 10,
    backend: 'wasm',
    faceMesh,
    useSkinMask: true,
    multiRoiFusion: true,
    enableTracker: { minBpm: 45, maxBpm: 180, numParticles: 240 },
    wasmJsUrl: rppgWasmJsUrl,
    wasmBinaryUrl: rppgWasmBinaryUrl,
    onError: (error) => console.warn('rPPG session error', error),
  });
}

function summarize(samples: RppgAppSnapshot[]): RppgMeasurement | null {
  const bpms = samples
    .map((sample) => sample.publishBpm)
    .filter((bpm): bpm is number => bpm !== null && Number.isFinite(bpm));
  if (bpms.length === 0) return null;

  const agreements = samples
    .map((sample) => sample.metrics.agreement)
    .filter((value): value is number => value !== undefined && Number.isFinite(value));

  return {
    source: 'rppg-web',
    version: SDK_VERSION,
    bpm: median(bpms),
    confidence: average(samples.map((sample) => clamp(sample.metrics.confidence))),
    signal_quality: average(samples.map((sample) => clamp(sample.metrics.signal_quality))),
    agreement: agreements.length > 0 ? average(agreements.map(clamp)) : null,
    reason_codes: [...new Set(samples.flatMap((sample) => sample.metrics.reason_codes ?? []))],
    stable_sample_count: samples.length,
  };
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
}
