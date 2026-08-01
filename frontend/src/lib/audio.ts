/**
 * 마이크 녹음 → 16-bit PCM WAV base64.
 *
 * MediaRecorder로 받은 뒤 브라우저 디코더로 풀고 16kHz 모노로 리샘플해서 보낸다.
 * eGeMAPS가 상정하는 표준 샘플레이트이고, 페이로드도 줄어든다.
 */

import { encodeWav, toBase64 } from './wav';

const TARGET_SAMPLE_RATE = 16000;

export class AudioRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  constructor(private readonly stream: MediaStream) {}

  start(): void {
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.recorder.start();
  }

  /** 녹음을 끝내고 WAV base64를 돌려준다. */
  async stop(): Promise<string> {
    const recorder = this.recorder;
    if (!recorder) throw new Error('녹음이 시작되지 않았습니다.');

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(this.chunks, { type: recorder.mimeType }));
      recorder.stop();
    });
    this.recorder = null;

    return toBase64(encodeWav(await decodeToMono16k(blob), TARGET_SAMPLE_RATE));
  }
}

/** 인코딩된 오디오 blob → 16kHz 모노 Float32. */
async function decodeToMono16k(blob: Blob): Promise<Float32Array> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const frameCount = Math.ceil(decoded.duration * TARGET_SAMPLE_RATE);

    const offline = new OfflineAudioContext(1, frameCount, TARGET_SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();

    const rendered = await offline.startRendering();
    return rendered.getChannelData(0);
  } finally {
    await context.close();
  }
}

/**
 * 오디오 + 비디오 스트림을 한 번에 얻는다.
 *
 * 사용자가 권한 팝업을 한 번만 보게 하려고 동시에 요청한다.
 * 영상은 화면 표시와 ROI 샘플링에만 쓰이고 브라우저 밖으로 나가지 않는다.
 */
export async function requestMedia(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
    video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
  });
}
