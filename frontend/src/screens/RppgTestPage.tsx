import { useEffect, useMemo, useRef, useState } from 'react';
import { compareRppg } from '../api/client';
import {
  lockCameraSettings,
  recordRgbSeries,
  RoiSampler,
  type RgbRecording,
  type RoiQuality,
} from '../lib/faceRoi';
import {
  IDLE_RPPG_QUALITY,
  RppgController,
  UNAVAILABLE_RPPG_QUALITY,
  type RppgQuality,
} from '../lib/rppg';
import type { RppgComparisonResult, RppgMeasurement } from '../types/contracts';

const MEASUREMENT_SECONDS = 15;
const MAX_WARMUP_SECONDS = 12;

type TestMode = 'web' | 'chrom' | 'simultaneous';
type TestPhase =
  | 'idle'
  | 'preparing_camera'
  | 'step_pending'
  | 'warming'
  | 'ready'
  | 'measuring'
  | 'submitting'
  | 'complete'
  | 'error';

interface ProtocolStep {
  set: number | null;
  mode: TestMode;
  label: string;
}

// 세트마다 먼저 실행하는 알고리즘을 바꿔 시간·안정화 편향을 한쪽에 몰지 않는다.
const PROTOCOL: ProtocolStep[] = [
  { set: 1, mode: 'web', label: '1세트 · rppg-web 단독' },
  { set: 1, mode: 'chrom', label: '1세트 · 서버 CHROM 단독' },
  { set: 2, mode: 'chrom', label: '2세트 · 서버 CHROM 단독' },
  { set: 2, mode: 'web', label: '2세트 · rppg-web 단독' },
  { set: 3, mode: 'web', label: '3세트 · rppg-web 단독' },
  { set: 3, mode: 'chrom', label: '3세트 · 서버 CHROM 단독' },
  { set: null, mode: 'simultaneous', label: '마지막 · 두 알고리즘 동시 측정' },
];

interface TestRecord extends RppgComparisonResult {
  id: string;
  captured_at: string;
  participant_id: string;
  condition: string;
  protocol_step: number;
  set: number | null;
  mode: TestMode;
  camera: {
    fps: number | null;
    duration_sec: number;
    sample_count: number | null;
    duplicates_skipped: number | null;
    mean_brightness: number | null;
    roi_count: number | null;
    width: number | null;
    height: number | null;
  };
}

export function RppgTestPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const controllerRef = useRef<RppgController | null>(null);
  const samplerRef = useRef<RoiSampler | null>(null);
  const warmupTimerRef = useRef<number | null>(null);

  const [phase, setPhase] = useState<TestPhase>('idle');
  const [stepIndex, setStepIndex] = useState(0);
  const [quality, setQuality] = useState<RppgQuality>(IDLE_RPPG_QUALITY);
  const [warmupTimedOut, setWarmupTimedOut] = useState(false);
  const [roiQuality, setRoiQuality] = useState<RoiQuality | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [participantId, setParticipantId] = useState('P01');
  const [condition, setCondition] = useState('normal_light_still');
  const [referenceBpm, setReferenceBpm] = useState('');
  const [records, setRecords] = useState<TestRecord[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const currentStep = PROTOCOL[stepIndex] ?? null;

  const clearWarmupTimer = () => {
    if (warmupTimerRef.current !== null) window.clearTimeout(warmupTimerRef.current);
    warmupTimerRef.current = null;
  };

  const disposeController = async () => {
    clearWarmupTimer();
    const controller = controllerRef.current;
    controllerRef.current = null;
    await controller?.dispose().catch(console.warn);
  };

  const cleanup = async () => {
    await disposeController();
    samplerRef.current?.dispose();
    samplerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  useEffect(() => {
    return () => {
      void cleanup();
    };
  }, []);

  const prepareCamera = async () => {
    setPhase('preparing_camera');
    setErrorMessage(null);
    try {
      await cleanup();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30 },
        },
      });
      streamRef.current = stream;

      const video = videoRef.current;
      if (!video) throw new Error('영상 요소를 찾을 수 없습니다.');
      video.srcObject = stream;
      await video.play();
      await lockCameraSettings(stream);
      samplerRef.current = await RoiSampler.create(video);
      setPhase('step_pending');
    } catch (error) {
      await cleanup();
      setErrorMessage(error instanceof Error ? error.message : '카메라 준비에 실패했습니다.');
      setPhase('error');
    }
  };

  const prepareStep = async () => {
    if (!currentStep || !streamRef.current) return;
    setErrorMessage(null);
    await disposeController();
    setQuality(IDLE_RPPG_QUALITY);
    setWarmupTimedOut(false);

    if (currentStep.mode === 'chrom') {
      // CHROM 단독 단계에서는 rppg-web 세션 자체를 만들지 않아 CPU/GPU 경쟁을 없앤다.
      setPhase('ready');
      return;
    }

    const video = videoRef.current;
    if (!video) return;
    setPhase('warming');
    try {
      let readyDuringCreate = false;
      let unavailableDuringCreate = false;
      const controller = await RppgController.create(
        video,
        (nextQuality) => {
          setQuality(nextQuality);
          if (nextQuality.ready) {
            readyDuringCreate = true;
            clearWarmupTimer();
            setPhase((previous) => (previous === 'warming' ? 'ready' : previous));
          }
        },
        () => {
          unavailableDuringCreate = true;
          clearWarmupTimer();
          setQuality(UNAVAILABLE_RPPG_QUALITY);
          setErrorMessage('rppg-web을 준비하지 못했습니다. 현재 단계를 다시 준비해주세요.');
          setPhase('step_pending');
        },
      );
      controllerRef.current = controller;
      // 실패 사례도 coverage에 들어가야 한다. ready를 무한정 기다려 좋은 사례만
      // 선택하지 않고, 고정 워밍업 뒤에는 낮은 품질 그대로 측정한다.
      if (!readyDuringCreate && !unavailableDuringCreate) {
        warmupTimerRef.current = window.setTimeout(() => {
          warmupTimerRef.current = null;
          setWarmupTimedOut(true);
          setPhase((previous) => (previous === 'warming' ? 'ready' : previous));
        }, MAX_WARMUP_SECONDS * 1000);
      }
    } catch (error) {
      await disposeController();
      setErrorMessage(error instanceof Error ? error.message : 'rppg-web 준비에 실패했습니다.');
      setPhase('step_pending');
    }
  };

  const measure = async () => {
    const step = currentStep;
    const sampler = samplerRef.current;
    const stream = streamRef.current;
    const parsedReference = Number(referenceBpm);
    if (!step || !sampler || !stream) return;
    if (!Number.isFinite(parsedReference) || parsedReference < 30 || parsedReference > 240) {
      setErrorMessage('비교 정확도를 계산하려면 현재 기준 심박을 30~240 BPM으로 입력해주세요.');
      return;
    }

    setPhase('measuring');
    setElapsedSec(0);
    setErrorMessage(null);
    try {
      let web: RppgMeasurement | null = null;
      let legacy: RgbRecording | null = null;

      if (step.mode === 'web') {
        const controller = controllerRef.current;
        if (!controller) throw new Error('rppg-web이 준비되지 않았습니다.');
        web = await controller.record(MEASUREMENT_SECONDS, setElapsedSec);
      } else if (step.mode === 'chrom') {
        legacy = await recordLegacy(sampler, setElapsedSec, setRoiQuality);
      } else {
        const controller = controllerRef.current;
        if (!controller) throw new Error('rppg-web이 준비되지 않았습니다.');
        [web, legacy] = await Promise.all([
          controller.record(MEASUREMENT_SECONDS, setElapsedSec),
          recordLegacy(sampler, setElapsedSec, setRoiQuality),
        ]);
      }

      setPhase('submitting');
      const comparison =
        web === null && legacy === null
          ? emptyComparison(parsedReference)
          : await compareRppg({
              rgb_series: legacy?.series ?? null,
              fps: legacy?.fps ?? 0,
              duration_sec: legacy?.durationSec ?? MEASUREMENT_SECONDS,
              rppg_web: web,
              reference_bpm: parsedReference,
            });

      const settings = stream.getVideoTracks()[0]?.getSettings();
      const meanBrightness = legacy ? calculateBrightness(legacy) : null;
      const record: TestRecord = {
        ...comparison,
        id: crypto.randomUUID(),
        captured_at: new Date().toISOString(),
        participant_id: participantId.trim() || 'unknown',
        condition: condition.trim() || 'unspecified',
        protocol_step: stepIndex + 1,
        set: step.set,
        mode: step.mode,
        camera: {
          fps: legacy?.fps ?? null,
          duration_sec: legacy?.durationSec ?? MEASUREMENT_SECONDS,
          sample_count: legacy?.series.length ?? null,
          duplicates_skipped: legacy?.duplicatesSkipped ?? null,
          mean_brightness: meanBrightness,
          roi_count: legacy ? sampler.quality.roiCount : null,
          width: settings?.width ?? null,
          height: settings?.height ?? null,
        },
      };
      setRecords((previous) => [...previous, record]);

      // 다음 CHROM 단독 단계에 rppg-web의 연산과 tracker 상태가 남지 않게 즉시 종료한다.
      await disposeController();
      if (stepIndex + 1 >= PROTOCOL.length) {
        setPhase('complete');
      } else {
        setStepIndex((previous) => previous + 1);
        setPhase('step_pending');
      }
    } catch (error) {
      await disposeController();
      setErrorMessage(error instanceof Error ? error.message : '비교 측정에 실패했습니다.');
      setPhase('step_pending');
    }
  };

  const resetProtocol = async () => {
    await disposeController();
    setRecords([]);
    setStepIndex(0);
    setQuality(IDLE_RPPG_QUALITY);
    setWarmupTimedOut(false);
    setRoiQuality(null);
    setErrorMessage(null);
    setPhase(streamRef.current ? 'step_pending' : 'idle');
  };

  const summary = useMemo(() => summarize(records), [records]);
  const cameraPrepared = streamRef.current !== null;

  return (
    <main className="app app--wide">
      <header className="diagnostic-head">
        <div>
          <p className="diagnostic-kicker">개발 전용 · 원시 RGB 비저장</p>
          <h1 className="panel__title">rPPG 교대 비교 프로토콜</h1>
        </div>
        <a className="button button--ghost" href="/">제품 화면</a>
      </header>

      <div className={`viewport ${cameraPrepared ? 'viewport--live' : 'viewport--idle'}`}>
        <video ref={videoRef} className="viewport__video" muted playsInline />
        {cameraPrepared && <div className="viewport__dot" aria-hidden="true" />}
      </div>

      {!cameraPrepared && phase === 'idle' && (
        <section className="panel">
          <p className="panel__lead">
            단독 측정을 세트별로 교대하고 마지막에 두 알고리즘을 동시에 실행합니다.
          </p>
          <p className="panel__note">
            각 단계마다 기준 장비의 현재 BPM을 입력해야 정확도와 MAE를 계산할 수 있습니다.
          </p>
          <button className="button" type="button" onClick={prepareCamera}>카메라 준비</button>
        </section>
      )}

      {phase === 'preparing_camera' && <section className="panel">카메라를 준비하고 있습니다…</section>}

      {cameraPrepared && currentStep && phase !== 'complete' && (
        <section className="panel diagnostic-controls">
          <div className="diagnostic-progress">
            <strong>{stepIndex + 1} / {PROTOCOL.length}</strong>
            <span>{currentStep.label}</span>
          </div>
          <label>
            참가자 ID
            <input value={participantId} onChange={(event) => setParticipantId(event.target.value)} disabled={phase === 'measuring' || phase === 'submitting'} />
          </label>
          <label>
            조건
            <select value={condition} onChange={(event) => setCondition(event.target.value)} disabled={phase === 'measuring' || phase === 'submitting'}>
              <option value="bright_light_still">밝은 정면광 + 정지</option>
              <option value="normal_light_still">보통 실내광 + 정지</option>
              <option value="low_light_still">어두운 조명 + 정지</option>
              <option value="small_head_motion">작은 고개 움직임</option>
              <option value="after_speaking">발화 직후 정지</option>
              <option value="post_exercise">가벼운 운동 직후</option>
            </select>
          </label>
          <label>
            현재 기준 장비 BPM
            <input type="number" min="30" max="240" value={referenceBpm} onChange={(event) => setReferenceBpm(event.target.value)} placeholder="매 단계 직전에 갱신" disabled={phase === 'measuring' || phase === 'submitting'} />
          </label>

          <div className="diagnostic-signals">
            {currentStep.mode !== 'chrom' && <span>rppg-web: {quality.message}</span>}
            {currentStep.mode !== 'web' && (
              <span>레거시 ROI: {roiQuality ? `최근 밝기 ${roiQuality.brightness.toFixed(0)} · ${roiQuality.roiCount}개` : '측정 시 확인'}</span>
            )}
          </div>

          {phase === 'step_pending' && (
            <button className="button" type="button" onClick={prepareStep}>{stepIndex + 1}단계 준비</button>
          )}
          {phase === 'warming' && <button className="button" type="button" disabled>rppg-web 워밍업 중 · 최대 {MAX_WARMUP_SECONDS}초</button>}
          {phase === 'ready' && (
            <button className="button" type="button" onClick={measure}>
              {warmupTimedOut && !quality.ready ? '낮은 품질 그대로 15초 측정' : '15초 측정 시작'}
            </button>
          )}
          {(phase === 'measuring' || phase === 'submitting') && (
            <p className="panel__lead">
              {phase === 'submitting' ? '결과를 계산하고 있습니다…' : `측정 중 ${Math.min(elapsedSec, MEASUREMENT_SECONDS).toFixed(1)} / ${MEASUREMENT_SECONDS}초`}
            </p>
          )}
          {errorMessage && <p className="diagnostic-error">{errorMessage}</p>}
        </section>
      )}

      {phase === 'complete' && (
        <section className="panel">
          <h2 className="layer__title">7단계 측정이 끝났습니다.</h2>
          <p className="panel__note">결과를 내려받은 뒤 조건을 바꾸거나 다음 참가자로 새 프로토콜을 시작하세요.</p>
          <button className="button" type="button" onClick={() => downloadCsv(records)}>CSV 내려받기</button>
          <button className="button button--ghost" type="button" onClick={resetProtocol}>새 프로토콜</button>
        </section>
      )}

      {phase === 'error' && (
        <section className="panel">
          <p className="diagnostic-error">{errorMessage}</p>
          <button className="button" type="button" onClick={prepareCamera}>카메라 다시 준비</button>
        </section>
      )}

      {records.length > 0 && (
        <>
          <section className="diagnostic-summary">
            <Metric label="진행" value={`${records.length}/${PROTOCOL.length}`} />
            <Metric label="web MAE (통과값)" value={formatBpm(summary.webMae)} />
            <Metric label="CHROM MAE (통과값)" value={formatBpm(summary.serverMae)} />
            <Metric label="web ≥ 0.4" value={formatPercent(summary.webPassRate)} />
            <Metric label="CHROM ≥ 0.4" value={formatPercent(summary.serverPassRate)} />
            <Metric label="동시 측정 BPM 차이" value={formatBpm(summary.simultaneousDifference)} />
          </section>

          <section className="panel diagnostic-results">
            <div className="diagnostic-actions">
              <h2 className="layer__title">측정 결과</h2>
              <button className="button button--ghost" type="button" onClick={() => downloadJson(records)}>JSON 내려받기</button>
              <button className="button button--ghost" type="button" onClick={() => downloadCsv(records)}>CSV 내려받기</button>
            </div>
            <div className="diagnostic-table-wrap">
              <table className="diagnostic-table">
                <thead><tr><th>단계</th><th>모드</th><th>기준</th><th>web</th><th>web 신뢰도</th><th>CHROM</th><th>CHROM 신뢰도</th><th>FPS</th><th>밝기</th></tr></thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id}>
                      <td>{record.protocol_step}</td><td>{record.mode}</td><td>{formatNumber(record.reference_bpm)}</td>
                      <td>{formatNumber(record.rppg_web?.bpm)}</td><td>{formatNumber(record.rppg_web?.confidence)}</td>
                      <td>{formatNumber(record.server_chrom?.bpm)}</td><td>{formatNumber(record.server_chrom?.confidence)}</td>
                      <td>{formatNumber(record.camera.fps)}</td><td>{formatNumber(record.camera.mean_brightness)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function recordLegacy(
  sampler: RoiSampler,
  onElapsed: (elapsed: number) => void,
  onQuality: (quality: RoiQuality) => void,
): Promise<RgbRecording> {
  return recordRgbSeries(sampler, MEASUREMENT_SECONDS, (elapsed, quality) => {
    onElapsed(elapsed);
    onQuality(quality);
  });
}

function calculateBrightness(recording: RgbRecording): number | null {
  if (recording.series.length === 0) return null;
  return recording.series.reduce((sum, sample) => sum + (sample.r + sample.g + sample.b) / 3, 0) / recording.series.length;
}

function emptyComparison(referenceBpm: number): RppgComparisonResult {
  return { server_chrom: null, rppg_web: null, reference_bpm: referenceBpm, server_absolute_error: null, web_absolute_error: null, bpm_difference: null };
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="diagnostic-metric"><span>{label}</span><strong>{value}</strong></div>;
}

function summarize(records: TestRecord[]) {
  const webRecords = records.filter((record) => record.mode !== 'chrom');
  const serverRecords = records.filter((record) => record.mode !== 'web');
  const webErrors = webRecords.flatMap((record) => record.web_absolute_error !== null && (record.rppg_web?.confidence ?? 0) >= 0.4 ? [record.web_absolute_error] : []);
  const serverErrors = serverRecords.flatMap((record) => record.server_absolute_error !== null && (record.server_chrom?.confidence ?? 0) >= 0.4 ? [record.server_absolute_error] : []);
  const simultaneous = records.find((record) => record.mode === 'simultaneous');
  return {
    webMae: averageOrNull(webErrors),
    serverMae: averageOrNull(serverErrors),
    webPassRate: webRecords.length === 0 ? null : webRecords.filter((record) => (record.rppg_web?.confidence ?? 0) >= 0.4).length / webRecords.length,
    serverPassRate: serverRecords.length === 0 ? null : serverRecords.filter((record) => (record.server_chrom?.confidence ?? 0) >= 0.4).length / serverRecords.length,
    simultaneousDifference: simultaneous?.bpm_difference ?? null,
  };
}

function averageOrNull(values: number[]): number | null {
  return values.length === 0 ? null : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

function formatBpm(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)} BPM`;
}

function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`;
}

function downloadJson(records: TestRecord[]) {
  download('rppg-comparison.json', JSON.stringify(records, null, 2), 'application/json');
}

function downloadCsv(records: TestRecord[]) {
  const header = [
    'id', 'captured_at', 'participant_id', 'condition', 'protocol_step', 'set', 'mode',
    'reference_bpm', 'web_bpm', 'web_confidence', 'web_signal_quality', 'web_agreement',
    'web_stable_sample_count', 'web_reason_codes', 'server_bpm', 'server_confidence',
    'server_snr_db', 'web_absolute_error', 'server_absolute_error', 'bpm_difference',
    'fps', 'sample_count', 'duplicates_skipped', 'mean_brightness', 'roi_count',
  ];
  const rows = records.map((record) => [
    record.id, record.captured_at, record.participant_id, record.condition,
    record.protocol_step, record.set, record.mode, record.reference_bpm,
    record.rppg_web?.bpm, record.rppg_web?.confidence, record.rppg_web?.signal_quality,
    record.rppg_web?.agreement, record.rppg_web?.stable_sample_count,
    record.rppg_web?.reason_codes.join('|'), record.server_chrom?.bpm,
    record.server_chrom?.confidence, record.server_chrom?.snr_db,
    record.web_absolute_error, record.server_absolute_error, record.bpm_difference,
    record.camera.fps, record.camera.sample_count, record.camera.duplicates_skipped,
    record.camera.mean_brightness, record.camera.roi_count,
  ]);
  const csv = [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
  download('rppg-comparison.csv', csv, 'text/csv;charset=utf-8');
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
