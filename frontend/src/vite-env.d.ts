/// <reference types="vite/client" />

/*
 * 전부 optional이다 — .env 없이도 앱이 돌아야 하므로 각 사용처에 기본값이 있다.
 * string으로 선언하면 없을 수 있다는 사실이 타입에서 사라진다.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** MediaPipe WASM 번들 위치. 모델만 내려받으며 영상은 브라우저 밖으로 나가지 않는다. */
  readonly VITE_MEDIAPIPE_WASM_URL?: string;
  readonly VITE_FACE_LANDMARKER_MODEL_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
