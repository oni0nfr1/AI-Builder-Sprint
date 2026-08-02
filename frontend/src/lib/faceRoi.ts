/**
 * 얼굴 ROI RGB 평균 시계열 추출 — rPPG의 입력.
 *
 * ★프라이버시 전제: 영상 프레임은 브라우저를 떠나지 않는다.
 *  여기서 얼굴 ROI의 평균 R/G/B 숫자만 뽑아 서버로 보낸다.
 *
 * 이마를 쓰는 이유: 피부가 평탄하고 표정 근육의 영향이 가장 적어 rPPG 표준 ROI다.
 * MediaPipe 로드에 실패해도 화면 중앙 고정 ROI로 계속 동작한다 — 얼굴 검출이
 * 없어도 사용자가 가이드에 얼굴을 맞추면 신호는 나온다.
 */

import type { FaceLandmarker } from '@mediapipe/tasks-vision';
import type { RgbSample } from '../types/contracts';

/** MediaPipe Face Mesh의 이마 영역 랜드마크. */
const FOREHEAD_LANDMARKS = [10, 67, 69, 104, 108, 151, 297, 299, 333, 337, 338];

const SAMPLE_CANVAS_SIZE = 64;

export interface RoiQuality {
  /** ROI 평균 밝기 0~255. 너무 어둡거나 포화되면 신호가 안 나온다. */
  brightness: number;
  faceDetected: boolean;
}

/**
 * rPPG는 피부 반사광의 미세한 맥동을 본다. 어두우면 그 변동이 양자화 노이즈에
 * 묻히고, 포화되면 아예 잘려 나간다. (실측: 밝기 45에서 confidence 0.05)
 */
export const BRIGHTNESS_TOO_DARK = 60;
export const BRIGHTNESS_TOO_BRIGHT = 235;

export interface QualityVerdict {
  ok: boolean;
  message: string;
}

/** 심박은 상상(정지) 구간에서만 재므로 이 판단도 그 구간에만 의미가 있다. */
export function describeQuality(quality: RoiQuality): QualityVerdict {
  if (!quality.faceDetected) {
    return { ok: false, message: '얼굴이 화면 안에 들어오도록 맞춰주세요.' };
  }
  if (quality.brightness < BRIGHTNESS_TOO_DARK) {
    return {
      ok: false,
      message: `너무 어두워요. 얼굴 쪽으로 빛이 오게 해주세요 (밝기 ${Math.round(
        quality.brightness,
      )} → ${BRIGHTNESS_TOO_DARK} 이상 필요).`,
    };
  }
  if (quality.brightness > BRIGHTNESS_TOO_BRIGHT) {
    return { ok: false, message: '빛이 너무 강해요. 조명을 조금 낮춰주세요.' };
  }
  return { ok: true, message: '신호가 잘 잡히고 있어요.' };
}

export class RoiSampler {
  private canvas = document.createElement('canvas');
  private ctx: CanvasRenderingContext2D;
  private landmarker: FaceLandmarker | null = null;
  private lastQuality: RoiQuality = { brightness: 0, faceDetected: false };

  // recordRgbSeries가 프레임 전진 여부를 보려면 요소에 접근할 수 있어야 한다.
  private constructor(readonly video: HTMLVideoElement) {
    this.canvas.width = SAMPLE_CANVAS_SIZE;
    this.canvas.height = SAMPLE_CANVAS_SIZE;
    const ctx = this.canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) throw new Error('캔버스를 만들 수 없습니다.');
    this.ctx = ctx;
  }

  static async create(video: HTMLVideoElement): Promise<RoiSampler> {
    const sampler = new RoiSampler(video);
    try {
      sampler.landmarker = await loadLandmarker();
    } catch (error) {
      // 얼굴 검출 없이도 고정 ROI로 계속 간다.
      console.warn('MediaPipe 로드 실패 — 중앙 고정 ROI로 대체합니다.', error);
    }
    return sampler;
  }

  get quality(): RoiQuality {
    return this.lastQuality;
  }

  /** 현재 프레임의 ROI 평균 RGB. 프레임이 아직 없으면 null. */
  sample(timestampMs: number): { r: number; g: number; b: number } | null {
    const { video } = this;
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return null;
    if (!video.videoWidth || !video.videoHeight) return null;

    const roi = this.resolveRoi(timestampMs);
    this.ctx.drawImage(
      video,
      roi.x,
      roi.y,
      roi.width,
      roi.height,
      0,
      0,
      SAMPLE_CANVAS_SIZE,
      SAMPLE_CANVAS_SIZE,
    );

    const { data } = this.ctx.getImageData(0, 0, SAMPLE_CANVAS_SIZE, SAMPLE_CANVAS_SIZE);
    let r = 0;
    let g = 0;
    let b = 0;
    const pixels = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      r += data[i];
      g += data[i + 1];
      b += data[i + 2];
    }
    r /= pixels;
    g /= pixels;
    b /= pixels;

    this.lastQuality = { brightness: (r + g + b) / 3, faceDetected: roi.fromFace };
    return { r, g, b };
  }

  /** 얼굴을 찾으면 이마 영역, 못 찾으면 화면 중앙 상단 고정 영역. */
  private resolveRoi(timestampMs: number) {
    const width = this.video.videoWidth;
    const height = this.video.videoHeight;

    if (this.landmarker) {
      try {
        const result = this.landmarker.detectForVideo(this.video, timestampMs);
        const landmarks = result.faceLandmarks?.[0];
        if (landmarks?.length) {
          const points = FOREHEAD_LANDMARKS.map((i) => landmarks[i]).filter(Boolean);
          if (points.length) {
            const xs = points.map((p) => p.x * width);
            const ys = points.map((p) => p.y * height);
            // 경계의 머리카락·눈썹이 섞이지 않도록 살짝 안쪽으로 줄인다.
            const inset = 0.15;
            const x0 = Math.min(...xs);
            const x1 = Math.max(...xs);
            const y0 = Math.min(...ys);
            const y1 = Math.max(...ys);
            const dx = (x1 - x0) * inset;
            const dy = (y1 - y0) * inset;
            return {
              x: x0 + dx,
              y: y0 + dy,
              width: Math.max(x1 - x0 - 2 * dx, 1),
              height: Math.max(y1 - y0 - 2 * dy, 1),
              fromFace: true,
            };
          }
        }
      } catch (error) {
        console.warn('얼굴 검출 실패 — 이번 프레임은 고정 ROI를 씁니다.', error);
      }
    }

    return {
      x: width * 0.35,
      y: height * 0.18,
      width: width * 0.3,
      height: height * 0.14,
      fromFace: false,
    };
  }

  dispose(): void {
    this.landmarker?.close();
    this.landmarker = null;
  }
}

let landmarkerPromise: Promise<FaceLandmarker> | null = null;

/*
 * 공개 CDN 주소라 비밀이 아니다. .env 없이도 돌아가야 한다 —
 * 값이 undefined면 MediaPipe 초기화가 실패하고 고정 중앙 ROI로 조용히 폴백해서,
 * 얼굴 추적이 죽은 줄 모르는 채 세션이 끝난다.
 */
const WASM_URL =
  import.meta.env.VITE_MEDIAPIPE_WASM_URL ??
  'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm';
const MODEL_URL =
  import.meta.env.VITE_FACE_LANDMARKER_MODEL_URL ??
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

/** 모델은 한 번만 받아 세션 내내 재사용한다. */
function loadLandmarker(): Promise<FaceLandmarker> {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const { FilesetResolver, FaceLandmarker: Landmarker } = await import(
        '@mediapipe/tasks-vision'
      );
      const fileset = await FilesetResolver.forVisionTasks(WASM_URL);
      return Landmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
        runningMode: 'VIDEO',
        numFaces: 1,
      });
    })();
  }
  return landmarkerPromise;
}

export interface RgbRecording {
  series: RgbSample[];
  fps: number;
  durationSec: number;
  /** 같은 카메라 프레임이라 건너뛴 횟수. 0에 가까울수록 샘플링이 정확하다. */
  duplicatesSkipped: number;
}

/**
 * 지정 시간 동안 ROI RGB를 모은다.
 *
 * ★같은 프레임을 두 번 읽으면 안 된다.
 * requestAnimationFrame은 디스플레이 주사율(60~120Hz)로 도는데 카메라는 보통 30fps라,
 * rAF마다 샘플링하면 절반 가까이가 직전 프레임의 복사본이 된다. 같은 값이 반복되면
 * 계단 모양 신호가 생기고, 그 계단이 만들어낸 가짜 고주파를 rPPG의 FFT가 심박으로
 * 잡는다 (실측: 15초에 731샘플 / 156bpm / SNR -9dB).
 *
 * requestVideoFrameCallback이 있으면 실제 프레임에만 콜백하고,
 * 없으면 currentTime이 움직였을 때만 샘플링해서 같은 효과를 낸다.
 *
 * 프레임 간격은 여전히 흔들리므로 실측 fps를 함께 돌려준다 —
 * 백엔드 rPPG가 균일 격자로 다시 샘플링할 때 필요하다.
 */
export function recordRgbSeries(
  sampler: RoiSampler,
  durationSec: number,
  onTick?: (elapsedSec: number, quality: RoiQuality) => void,
): Promise<RgbRecording> {
  return new Promise((resolve) => {
    const series: RgbSample[] = [];
    const startMs = performance.now();
    const video = sampler.video;
    // 표준 타입에는 필수로 선언돼 있지만 Firefox 등에는 아직 없다. 런타임에서 확인한다.
    const useFrameCallback = typeof video.requestVideoFrameCallback === 'function';

    let lastVideoTime = -1;
    let duplicatesSkipped = 0;
    let settled = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(watchdog);
      const elapsedSec = (performance.now() - startMs) / 1000;
      resolve({
        series,
        fps: series.length > 1 ? series.length / elapsedSec : 0,
        durationSec: elapsedSec,
        duplicatesSkipped,
      });
    };

    // 카메라가 멈추면 requestVideoFrameCallback은 영영 오지 않는다.
    // 세션이 통째로 멈추느니 모은 만큼이라도 들고 나간다.
    const watchdog = setTimeout(finish, (durationSec + 2) * 1000);

    const step = () => {
      if (settled) return;
      const nowMs = performance.now();
      const elapsedSec = (nowMs - startMs) / 1000;

      // requestVideoFrameCallback은 새 프레임에만 오므로 중복 검사가 필요 없다.
      if (useFrameCallback || video.currentTime !== lastVideoTime) {
        lastVideoTime = video.currentTime;
        const rgb = sampler.sample(nowMs);
        if (rgb) series.push({ t: elapsedSec, ...rgb });
      } else {
        duplicatesSkipped += 1;
      }
      onTick?.(elapsedSec, sampler.quality);

      if (elapsedSec >= durationSec) {
        finish();
        return;
      }
      schedule();
    };

    const schedule = () => {
      if (useFrameCallback) video.requestVideoFrameCallback(step);
      else requestAnimationFrame(step);
    };
    schedule();
  });
}
