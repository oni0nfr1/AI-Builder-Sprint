import { useEffect, useRef } from 'react';
import { CaptureStage } from './components/CaptureStage';
import { useSessionFlow } from './hooks/useSessionFlow';
import { totalDurationSec } from './lib/sessionFlow';
import { DecisionInput } from './screens/DecisionInput';
import { ReportView } from './screens/ReportView';

export default function App() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { state, start, runAll, submitAnnotation, reset, stopMedia } =
    useSessionFlow(videoRef);

  // 탭을 떠나거나 앱이 사라져도 카메라·마이크가 켜져 있으면 안 된다.
  useEffect(() => stopMedia, [stopMedia]);

  const capturing = state.phase === 'capturing';
  const ready = state.phase === 'ready';
  const currentStep = capturing ? state.steps[state.stepIndex] : null;
  // 준비 화면에서도 신호를 보여준다 — 어두운 채로 시작하면 심박이 통째로 버려진다.
  const preflight = ready ? state.quality : null;

  return (
    <main className="app">
      {/*
        영상 요소는 트리의 고정된 자리에 항상 마운트된 채로 둔다.
        조건부로 위치를 옮기면 언마운트되면서 srcObject 연결이 끊긴다.
        영상은 화면 표시와 ROI 샘플링에만 쓰이고 브라우저 밖으로 나가지 않는다.
      */}
      <div className={`viewport ${capturing || ready ? 'viewport--live' : 'viewport--idle'}`}>
        <video ref={videoRef} className="viewport__video" muted playsInline />
        {currentStep?.phase === 'imagine' && (
          // 시선을 한 곳에 두면 머리 움직임이 줄어 rPPG 신호가 안정된다.
          <div className="viewport__dot" aria-hidden="true" />
        )}
        {currentStep?.phase === 'speak' && (
          <div className="viewport__mic" aria-hidden="true">
            ●
          </div>
        )}
      </div>

      {(state.phase === 'input' || state.phase === 'preparing') && (
        <DecisionInput onSubmit={start} disabled={state.phase === 'preparing'} />
      )}

      {state.phase === 'ready' && state.decision && (
        <div className="panel">
          <h1 className="panel__title">{state.decision.title}</h1>
          <ul className="panel__options">
            {state.decision.options.map((option) => (
              <li key={option.id}>{option.label}</li>
            ))}
          </ul>
          <p className="panel__lead">
            먼저 평소 상태를 잠깐 재고, 두 선택지를 하나씩 떠올려볼 거예요.
            <br />
            전부 합쳐 약 {Math.round(totalDurationSec(state.steps))}초입니다.
          </p>
          <p className="panel__note">
            정답을 맞히는 시간이 아니에요. 떠오르는 대로 두시면 됩니다.
          </p>
          {preflight && (
            <p className={`signal ${preflight.ready ? 'signal--ok' : 'signal--warn'}`}>
              {preflight.ready ? '●' : '○'} {preflight.message}
            </p>
          )}
          {/*
            신호가 나빠도 막지는 않는다 — 조명을 못 바꾸는 상황도 있고,
            심박이 빠져도 음성만으로 파이프라인은 돈다. 다만 그 선택을
            사용자가 알고 하도록 버튼 문구로 알린다.
          */}
          <button className="button" type="button" onClick={runAll}>
            {preflight?.ready ? '시작' : '이대로 시작'}
          </button>
        </div>
      )}

      {currentStep && (
        <CaptureStage
          step={currentStep}
          stepIndex={state.stepIndex}
          stepCount={state.steps.length}
          elapsedSec={state.elapsedSec}
          quality={state.quality}
        />
      )}

      {state.phase === 'analyzing' && (
        <div className="panel">
          <p className="panel__lead">기록을 정리하고 있어요…</p>
        </div>
      )}

      {state.phase === 'report' && state.report && state.decision && (
        <ReportView
          report={state.report}
          decision={state.decision}
          onSubmit={submitAnnotation}
        />
      )}

      {state.phase === 'done' && (
        <div className="panel">
          <h1 className="panel__title">기록했어요.</h1>
          <p className="panel__lead">
            일주일 뒤에 다시 물어볼게요 — 그때 어떤 선택을 했고, 지금은 어떤지.
            <br />그 대조가 쌓이면 내 직관이 얼마나 믿을 만한지 보이기 시작해요.
          </p>
          <button className="button" type="button" onClick={reset}>
            새 고민 기록하기
          </button>
        </div>
      )}

      {state.phase === 'error' && (
        <div className="panel">
          <h1 className="panel__title">문제가 생겼어요</h1>
          <p className="panel__lead">{state.errorMessage}</p>
          <button className="button" type="button" onClick={reset}>
            처음으로
          </button>
        </div>
      )}
    </main>
  );
}
