/**
 * 브라우저 STT (Web Speech API).
 *
 * Chrome 한국어만 지원한다. 없으면 transcript가 null로 가고 파이프라인은 그대로 돈다 —
 * 발화 내용은 [5] 리포트의 부가 재료일 뿐이고, 판정은 음향 특징에서 나오기 때문이다.
 */

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult:
    | ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void)
    | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const isSttSupported = (): boolean => getRecognitionCtor() !== null;

/** 다시 띄워도 소용없는 오류. 무한 재시작을 막는다. */
const FATAL_ERRORS = new Set(['not-allowed', 'service-not-allowed', 'audio-capture']);

/** onend가 끝내 오지 않는 경우가 있어 무한정 기다리지 않는다. */
const FLUSH_TIMEOUT_MS = 1500;

export class Transcriber {
  private recognition: SpeechRecognitionLike | null = null;
  private parts: string[] = [];
  private running = false;
  private resolveEnd: (() => void) | null = null;

  /** 마지막 오류 코드. 조용히 실패하면 원인을 알 수 없으므로 남긴다. */
  lastError: string | null = null;

  start(): void {
    const Ctor = getRecognitionCtor();
    if (!Ctor) {
      this.lastError = 'unsupported';
      return;
    }
    this.parts = [];
    this.lastError = null;
    this.running = true;
    this.spawn(Ctor);
  }

  private spawn(Ctor: SpeechRecognitionCtor): void {
    const recognition = new Ctor();
    recognition.lang = 'ko-KR';
    recognition.continuous = true;
    recognition.interimResults = false;

    // 이 인식 세션이 지금까지 확정한 문장들. onend에서 통째로 넘긴다.
    let current: string[] = [];

    recognition.onresult = (event) => {
      current = [];
      for (let i = 0; i < event.results.length; i += 1) {
        const alternative = event.results[i][0];
        if (alternative?.transcript) current[i] = alternative.transcript;
      }
    };

    recognition.onerror = (event) => {
      this.lastError = event?.error ?? 'unknown';
    };

    recognition.onend = () => {
      this.parts.push(...current.filter(Boolean));
      current = [];

      /*
       * Chrome은 continuous를 켜도 침묵이 이어지면 스스로 끝낸다.
       * 그대로 두면 그 뒤의 발화가 통째로 사라지므로, 구간이 끝날 때까지 다시 띄운다.
       */
      if (this.running && !FATAL_ERRORS.has(this.lastError ?? '')) {
        this.spawn(Ctor);
        return;
      }
      this.recognition = null;
      this.resolveEnd?.();
      this.resolveEnd = null;
    };

    this.recognition = recognition;
    try {
      recognition.start();
    } catch (error) {
      // 이미 시작된 인식기에 start()를 부르면 던진다. 치명적이지 않다.
      this.lastError = error instanceof Error ? error.message : 'start-failed';
    }
  }

  /**
   * 녹음을 끝내고 인식 결과를 돌려준다.
   *
   * ★비동기여야 한다. recognition.stop() 직후 결과를 읽으면 거의 항상 비어 있다 —
   * 확정된 문장은 그 뒤에 onresult/onend 이벤트로 오기 때문이다.
   */
  async stop(): Promise<string | null> {
    const recognition = this.recognition;
    this.running = false;
    if (!recognition) return this.collect();

    await Promise.race([
      new Promise<void>((resolve) => {
        this.resolveEnd = resolve;
        recognition.stop();
      }),
      new Promise<void>((resolve) => window.setTimeout(resolve, FLUSH_TIMEOUT_MS)),
    ]);

    if (this.recognition) {
      // 시간 안에 안 끝났다 — 마이크를 붙들고 있지 않도록 강제로 끊는다.
      this.recognition.abort();
      this.recognition = null;
    }
    this.resolveEnd = null;
    return this.collect();
  }

  private collect(): string | null {
    const text = this.parts.filter(Boolean).join(' ').trim();
    this.parts = [];
    return text || null;
  }
}
