/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  /** MediaPipe WASM 번들 위치. 모델만 내려받으며 영상은 브라우저 밖으로 나가지 않는다. */
  readonly VITE_MEDIAPIPE_WASM_URL: string;
  readonly VITE_FACE_LANDMARKER_MODEL_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
