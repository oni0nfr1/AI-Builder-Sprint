/**
 * [0] 고민 입력.
 *
 * 예시 문구는 형식만 보여주고 내용은 유도하지 않는다.
 */

import { useState } from 'react';

interface Props {
  onSubmit: (rawInput: string) => void;
  disabled?: boolean;
}

const PLACEHOLDER = '예) 이직할지 지금 회사에 남을지 고민이에요';

export function DecisionInput({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('');
  const trimmed = value.trim();

  return (
    <form
      className="panel"
      onSubmit={(event) => {
        event.preventDefault();
        if (trimmed) onSubmit(trimmed);
      }}
    >
      <h1 className="panel__title">지금 무엇을 고민하고 계세요?</h1>
      <p className="panel__lead">
        한 문장이면 충분해요. 두 선택지가 드러나게 적어주세요.
      </p>

      <textarea
        className="panel__input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={PLACEHOLDER}
        rows={3}
        disabled={disabled}
      />

      <button className="button" type="submit" disabled={disabled || !trimmed}>
        {disabled ? '준비하는 중…' : '시작하기'}
      </button>

      <p className="panel__note">
        약 80초가 걸려요. 카메라와 마이크를 사용합니다 —
        <strong> 영상은 이 브라우저를 떠나지 않고</strong>, 얼굴에서 읽은 숫자만 전송됩니다.
      </p>
    </form>
  );
}
