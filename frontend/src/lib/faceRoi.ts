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

/**
 * MediaPipe Face Mesh 랜드마크로 잡는 피부 영역들.
 *
 * ★이마만 쓰지 않고 볼까지 더한다. 평균 내는 픽셀이 많을수록 잡음이 1/√N 로
 * 줄어드는데, 실측 맥동 진폭이 0.19% 수준이라 이 이득이 그대로 SNR 이 된다.
 * 이마는 표정 근육 영향이 가장 적어 여전히 주력이고, 볼은 보강이다.
 */
const ROI_LANDMARKS: { name: string; indices: number[]; inset: number }[] = [
  { name: 'forehead', indices: [10, 67, 69, 104, 108, 151, 297, 299, 333, 337, 338], inset: 0.15 },
  // 볼은 코·입·머리카락 경계가 가까워 더 크게 줄여 안쪽만 쓴다.
  { name: 'cheekL', indices: [50, 101, 117, 118, 123, 187, 205, 36], inset: 0.25 },
  { name: 'cheekR', indices: [280, 330, 346, 347, 352, 411, 425, 266], inset: 0.25 },
];

const SAMPLE_CANVAS_SIZE = 64;

/** 이보다 작으면 얼굴이 멀거나 검출이 흔들린 것이다. 평균에 넣으면 잡음만 는다. */
const MIN_ROI_PIXELS = 12;

export interface RoiQuality {
  /** ROI 평균 밝기 0~255. 너무 어둡거나 포화되면 신호가 안 나온다. */
  brightness: number;
  faceDetected: boolean;
  /** 이번 프레임에 실제로 쓰인 영역 수 (이마 + 양 볼이면 3). 진단용. */
  roiCount: number;
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

/**
 * 카메라 자동보정을 잠근다. ★rPPG 품질에 직결된다.
 *
 * 오디오에서 `autoGainControl: false` 를 한 것과 정확히 같은 이유다.
 * rPPG 는 피부 밝기의 미세 변동(실측 0.19% 수준)을 재는데, 자동 노출과
 * 화이트밸런스가 켜져 있으면 카메라가 그 변동을 실시간으로 상쇄한다 —
 * 측정 대상을 카메라가 지우는 셈이다.
 *
 * 자동보정이 자리를 잡은 뒤에 잠가야 하므로 잠깐 기다린 다음 건다.
 * 지원하지 않는 카메라가 많으므로 capabilities 를 보고 되는 것만 적용한다.
 */
export async function lockCameraSettings(stream: MediaStream): Promise<string[]> {
  const [track] = stream.getVideoTracks();
  if (!track) return [];

  // 자동 노출·화이트밸런스가 수렴할 시간을 준다. 켜자마자 잠그면 어두운 채로 굳는다.
  await new Promise((resolve) => setTimeout(resolve, 1200));

  // 표준 타입에 없는 확장 필드다 (Image Capture 명세).
  const capabilities = track.getCapabilities() as Record<string, unknown>;
  const wanted: Record<string, string> = {
    exposureMode: 'manual',
    whiteBalanceMode: 'manual',
    focusMode: 'manual',
  };

  const locked: string[] = [];
  for (const [key, value] of Object.entries(wanted)) {
    const supported = capabilities[key];
    if (!Array.isArray(supported) || !supported.includes(value)) continue;
    try {
      await track.applyConstraints({ advanced: [{ [key]: value }] } as MediaTrackConstraints);
      locked.push(key);
    } catch {
      // 이 카메라가 거부했다. 나머지는 계속 시도한다.
    }
  }
  return locked;
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

interface RoiRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 랜드마크들을 감싸는 사각형에서 경계를 안쪽으로 줄인 영역. */
function boundingRect(
  points: { x: number; y: number }[],
  width: number,
  height: number,
  inset: number,
): RoiRect | null {
  const xs = points.map((p) => p.x * width);
  const ys = points.map((p) => p.y * height);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);

  // 경계의 머리카락·눈썹·콧방울이 섞이지 않도록 안쪽으로 줄인다.
  const dx = (x1 - x0) * inset;
  const dy = (y1 - y0) * inset;
  const rect = {
    x: x0 + dx,
    y: y0 + dy,
    width: x1 - x0 - 2 * dx,
    height: y1 - y0 - 2 * dy,
  };

  // 화면 밖으로 나가면 잘라낸다. 얼굴이 가장자리에 있을 때 생긴다.
  const left = Math.max(0, rect.x);
  const top = Math.max(0, rect.y);
  const right = Math.min(width, rect.x + rect.width);
  const bottom = Math.min(height, rect.y + rect.height);
  if (right - left < MIN_ROI_PIXELS || bottom - top < MIN_ROI_PIXELS) return null;

  return { x: left, y: top, width: right - left, height: bottom - top };
}

export class RoiSampler {
  private canvas = document.createElement('canvas');
  private ctx: CanvasRenderingContext2D;
  private landmarker: FaceLandmarker | null = null;
  private lastQuality: RoiQuality = { brightness: 0, faceDetected: false, roiCount: 0 };

  // recordRgbSeries가 프레임 전진 여부를 보려면 요소에 접근할 수 있어야 한다.
  private constructor(readonly video: HTMLVideoElement) {
    this.canvas.width = SAMPLE_CANVAS_SIZE;
    this.canvas.height = SAMPLE_CANVAS_SIZE;
    const ctx = this.canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) throw new Error('캔버스를 만들 수 없습니다.');
    this.ctx = ctx;
    // 축소할 때 원본 픽셀을 제대로 평균하게 한다. 이 평균이 곧 잡음 억제다.
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = 'high';
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

  /**
   * 현재 프레임의 ROI 평균 RGB. 프레임이 아직 없으면 null.
   *
   * 여러 ROI를 **넓이로 가중 평균**한다 — 전체 피부 픽셀을 한꺼번에 평균한 것과
   * 같아지도록. 넓은 영역이 그만큼 많은 실제 픽셀을 담고 있기 때문이다.
   */
  sample(timestampMs: number): { r: number; g: number; b: number } | null {
    const { video } = this;
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return null;
    if (!video.videoWidth || !video.videoHeight) return null;

    const { rects, fromFace } = this.resolveRois(timestampMs);
    if (rects.length === 0) return null;

    let r = 0;
    let g = 0;
    let b = 0;
    let totalWeight = 0;
    let used = 0;

    for (const rect of rects) {
      const mean = this.meanOf(rect);
      if (mean === null) continue;
      const weight = rect.width * rect.height;
      r += mean.r * weight;
      g += mean.g * weight;
      b += mean.b * weight;
      totalWeight += weight;
      used += 1;
    }
    if (totalWeight <= 0) return null;

    r /= totalWeight;
    g /= totalWeight;
    b /= totalWeight;

    this.lastQuality = { brightness: (r + g + b) / 3, faceDetected: fromFace, roiCount: used };
    return { r, g, b };
  }

  private meanOf(rect: RoiRect): { r: number; g: number; b: number } | null {
    if (rect.width < MIN_ROI_PIXELS || rect.height < MIN_ROI_PIXELS) return null;
    this.ctx.drawImage(
      this.video,
      rect.x,
      rect.y,
      rect.width,
      rect.height,
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
    return { r: r / pixels, g: g / pixels, b: b / pixels };
  }

  /** 얼굴을 찾으면 이마 + 양 볼, 못 찾으면 화면 중앙 상단 고정 영역 하나. */
  private resolveRois(timestampMs: number): { rects: RoiRect[]; fromFace: boolean } {
    const width = this.video.videoWidth;
    const height = this.video.videoHeight;

    if (this.landmarker) {
      try {
        const result = this.landmarker.detectForVideo(this.video, timestampMs);
        const landmarks = result.faceLandmarks?.[0];
        if (landmarks?.length) {
          const rects: RoiRect[] = [];
          for (const region of ROI_LANDMARKS) {
            const points = region.indices.map((i) => landmarks[i]).filter(Boolean);
            if (points.length < 3) continue;
            const rect = boundingRect(points, width, height, region.inset);
            if (rect) rects.push(rect);
          }
          // 볼을 못 잡아도 이마 하나면 계속 간다 — 예전 동작 그대로다.
          if (rects.length > 0) return { rects, fromFace: true };
        }
      } catch (error) {
        console.warn('얼굴 검출 실패 — 이번 프레임은 고정 ROI를 씁니다.', error);
      }
    }

    return {
      rects: [
        {
          x: width * 0.35,
          y: height * 0.18,
          width: width * 0.3,
          height: height * 0.14,
        },
      ],
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
