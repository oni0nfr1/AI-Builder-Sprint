# 직관 노트 — 프론트엔드

React + Vite (웹). 설계는 `../CLAUDE.md`, 계약은 `../docs/CONTRACTS.md`.

## 실행

```bash
npm install
cp .env.example .env      # 백엔드 주소 확인
npm run dev               # http://localhost:5173
```

백엔드가 `http://localhost:8000`에 떠 있어야 한다.

`getUserMedia`는 보안 컨텍스트를 요구한다. `localhost`는 예외로 허용되지만,
다른 기기에서 접속해 테스트하려면 https가 필요하다.

## 구조

```
src/
  types/contracts.ts     계약 (backend/app/schemas 와 1:1)
  api/client.ts          { ok, data, error } 언래핑
  lib/
    wav.ts               Float32 → 16-bit PCM WAV base64
    audio.ts             마이크 녹음 → 16kHz 모노 WAV
    rppg.ts              ★주 경로 — rppg-web 세션 → 브라우저 내 심박/품질 요약
    faceRoi.ts           폴백 — MediaPipe 얼굴 ROI → RGB 평균 시계열 (서버가 분석)
                         + 카메라 자동보정 잠금 (두 경로 모두에 필요)
    sessionFlow.ts       세션 스텝 정의 (약 80초)
  hooks/useSessionFlow.ts  상태 머신
  components/CaptureStage.tsx
  screens/DecisionInput.tsx, ReportView.tsx
```

## 설계상 지켜야 할 것

**영상은 브라우저를 떠나지 않는다.** `rppg.ts`가 브라우저 안에서 영상을 분석하고
서버에는 BPM과 품질 요약만 보낸다. 프레임이나 RGB 시계열, 인코딩된 영상을 서버로 보내는 코드를 추가하지 마라 —
프라이버시는 기능이 아니라 전제다.

**측정 중 BPM은 사용자에게 보여주지 않는다.** 숫자를 본 반응이 현재 측정과 다음
선택지에 영향을 줄 수 있으므로 UI에는 측정 품질과 행동 안내만 표시한다.

**오디오는 16-bit PCM WAV로 보낸다.** `MediaRecorder` 기본 출력(WebM/Opus)을 그대로
보내면 서버가 ffmpeg 없이 못 읽는다. `audio.ts`가 브라우저 디코더로 풀어 WAV로 바꾼다.

**`autoGainControl: false`.** 자동 게인이 켜져 있으면 음량 지표가 무의미해진다.

**`<video>` 요소는 App의 고정된 자리에 항상 마운트해둔다.** 조건부로 위치를 옮기면
언마운트되면서 `srcObject` 연결과 rPPG 세션 바인딩이 끊긴다.

**리포트 화면은 `Report`의 필드만 렌더링한다.** 내부 판정(`Verdict`)은 서버가 보내지
않는다. 우리가 판정했다는 사실이 노출되면 사용자는 다시 결정을 아웃소싱하게 된다.

**리포트 순서를 바꾸지 마라.** 상태 고지 → 관찰 → 태깅 → 자기 진술. 상태가 프레임이라
먼저 와야 하고, 자기 진술이 마지막이라야 사용자의 결정이 된다.
