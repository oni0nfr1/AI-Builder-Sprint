/**
 * 마이크 녹음 → 16-bit PCM WAV base64.
 *
 * AudioWorklet으로 raw PCM을 직접 모은다. MediaRecorder를 쓰지 않는 이유:
 * MediaRecorder는 재생 시간이 헤더에 없는 스트리밍용 WebM을 만드는데,
 * decodeAudioData가 그걸 거부해서 "Unable to decode audio data"로 죽는다.
 * 애초에 우리에게 필요한 건 raw PCM이라 인코딩→디코딩 왕복 자체가 낭비였다.
 *
 * 16kHz 모노로 리샘플해서 보낸다 — eGeMAPS가 상정하는 표준 샘플레이트이고 페이로드도 줄어든다.
 */

import { encodeWav, toBase64 } from './wav';

const TARGET_SAMPLE_RATE = 16000;

/** 오디오 스레드에서 도는 코드. 파일로 분리하지 않고 Blob URL로 올린다. */
const WORKLET_SOURCE = `
class PcmCollector extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(4096);
    this.filled = 0;
    this.done = false;
    // 메인 스레드가 끝났다고 알리면 남은 꼬리를 비우고 종료 신호를 보낸다.
    this.port.onmessage = () => {
      if (this.filled > 0) this.port.postMessage(this.buffer.slice(0, this.filled));
      this.port.postMessage(null);
      this.done = true;
    };
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i += 1) {
        this.buffer[this.filled] = channel[i];
        this.filled += 1;
        if (this.filled === this.buffer.length) {
          this.port.postMessage(this.buffer);
          this.buffer = new Float32Array(4096);
          this.filled = 0;
        }
      }
    }
    return !this.done;
  }
}
registerProcessor('pcm-collector', PcmCollector);
`;

export class AudioRecorder {
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private chunks: Float32Array[] = [];
  private onEnd: (() => void) | null = null;

  constructor(private readonly stream: MediaStream) {}

  async start(): Promise<void> {
    this.chunks = [];

    /*
     * 오디오 트랙만 뽑아 새 스트림으로 넘긴다. requestMedia()가 주는 원본에는
     * 비디오 트랙도 들어 있는데, 소스 노드에 그대로 물리면 불필요한 트랙까지 붙는다.
     */
    const audioTracks = this.stream.getAudioTracks();
    if (audioTracks.length === 0) throw new Error('마이크 트랙이 없습니다.');

    const context = new AudioContext();
    if (context.state === 'suspended') await context.resume();

    const url = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: 'application/javascript' }),
    );
    try {
      await context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }

    const node = new AudioWorkletNode(context, 'pcm-collector');
    node.port.onmessage = (event) => {
      if (event.data === null) {
        this.onEnd?.();
        return;
      }
      this.chunks.push(event.data as Float32Array);
    };

    const source = context.createMediaStreamSource(new MediaStream(audioTracks));
    source.connect(node);
    // destination까지 잇지 않는다 — 이으면 자기 목소리가 스피커로 새어 나온다.
    // 워크릿은 연결만으로도 process()가 돌므로 출력은 필요 없다.

    this.context = context;
    this.source = source;
    this.node = node;
  }

  /** 녹음을 끝내고 WAV base64를 돌려준다. */
  async stop(): Promise<string> {
    const { context, source, node } = this;
    if (!context || !source || !node) throw new Error('녹음이 시작되지 않았습니다.');

    // 워크릿에 남은 꼬리(최대 4096프레임)까지 받고 끝낸다.
    await new Promise<void>((resolve) => {
      this.onEnd = resolve;
      node.port.postMessage('flush');
    });

    const sampleRate = context.sampleRate;
    const merged = concat(this.chunks);
    this.chunks = [];

    source.disconnect();
    node.disconnect();
    node.port.onmessage = null;
    this.context = this.source = this.node = null;
    this.onEnd = null;

    try {
      if (merged.length === 0) {
        throw new Error('녹음된 소리가 없습니다. 마이크가 켜져 있는지 확인해주세요.');
      }
      const buffer = context.createBuffer(1, merged.length, sampleRate);
      buffer.copyToChannel(merged, 0);
      return toBase64(encodeWav(await resample(buffer), TARGET_SAMPLE_RATE));
    } finally {
      await context.close();
    }
  }
}

// 반환 타입은 추론에 맡긴다 — Float32Array로 적으면 버퍼 타입이 ArrayBufferLike로
// 넓어져서 copyToChannel(ArrayBuffer 전용)이 거부한다.
function concat(chunks: Float32Array[]) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

/** 마이크 기본 샘플레이트(보통 48kHz) → 16kHz. */
async function resample(buffer: AudioBuffer): Promise<Float32Array> {
  const frameCount = Math.max(
    1,
    Math.round((buffer.length * TARGET_SAMPLE_RATE) / buffer.sampleRate),
  );
  const offline = new OfflineAudioContext(1, frameCount, TARGET_SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  return (await offline.startRendering()).getChannelData(0);
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
    video: {
      // ROI 픽셀이 많을수록 평균이 잡음을 지운다 (노이즈는 1/√N 로 준다).
      // 실측 맥동 진폭이 0.19% 수준이라 픽셀 수가 곧 신호 품질이다.
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30 },
    },
  });
}
