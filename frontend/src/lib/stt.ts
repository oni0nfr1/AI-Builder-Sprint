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
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: unknown) => void) | null;
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

export class Transcriber {
  private recognition: SpeechRecognitionLike | null = null;
  private parts: string[] = [];

  start(): void {
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;

    this.parts = [];
    const recognition = new Ctor();
    recognition.lang = 'ko-KR';
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      for (let i = 0; i < event.results.length; i += 1) {
        const alternative = event.results[i][0];
        if (alternative?.transcript) this.parts[i] = alternative.transcript;
      }
    };
    recognition.onerror = () => {
      // 인식 실패는 치명적이지 않다 — 음향 특징만으로 판정이 가능하다.
    };

    this.recognition = recognition;
    recognition.start();
  }

  stop(): string | null {
    if (!this.recognition) return null;
    this.recognition.stop();
    this.recognition = null;
    const text = this.parts.filter(Boolean).join(' ').trim();
    return text || null;
  }
}
