# AI Builder Sprint 2026

> 총 168시간, AI와 함께 만드는 도전

## 프로젝트 — 직관 노트

고민 중인 두 선택지를 말하고 상상할 때 나타나는 음성·심박 반응을 관찰해,
사용자가 자신의 직관을 직접 해석하도록 돕는 메타인지 훈련 웹앱입니다.
AI가 결정을 추천하거나 감정을 단정하지 않고, 측정된 차이와 질문만 제공합니다.

### 로컬 실행 가이드

#### 준비물

- Python 3.11 이상
- Node.js 20 이상과 npm
- 카메라와 마이크를 사용할 수 있는 Chrome 계열 브라우저

백엔드와 프론트엔드는 서로 다른 터미널에서 실행합니다.

#### 1. 백엔드 실행

macOS/Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

백엔드가 실행되면 다음 주소를 확인할 수 있습니다.

- 상태 확인: http://localhost:8000/health
- API 문서: http://localhost:8000/docs

`backend/.env`의 `UPSTAGE_API_KEY`는 선택 사항입니다. 키가 없거나 Solar 호출에
실패하면 고민 파싱과 리포트 생성은 규칙 기반 폴백으로 동작합니다.

STT는 기본적으로 `faster-whisper`의 `base` 모델을 사용하며 첫 실행에 약 145MB를
다운로드합니다. 모델 다운로드가 어려운 환경에서는 아래처럼 비활성화할 수 있습니다.

```env
STT_ENABLED=false
```

#### 2. 프론트엔드 실행

macOS/Linux:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Windows PowerShell:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

브라우저에서 http://localhost:5173 에 접속하고 카메라·마이크 권한을 허용합니다.
프론트엔드가 다른 백엔드 주소를 사용해야 한다면 `frontend/.env`를 수정합니다.

```env
VITE_API_BASE_URL=http://localhost:8000
```

> `getUserMedia`는 보안 컨텍스트에서만 동작합니다. `localhost`는 허용되지만,
> 다른 기기에서 접속하거나 원격 배포할 때는 HTTPS가 필요합니다.

#### 3. 테스트

백엔드:

```bash
cd backend
python -m pytest -q
```

프론트엔드:

```bash
cd frontend
npm run typecheck
npm run build
```

세부 구조와 개발 시 주의사항은 [`backend/README.md`](backend/README.md),
[`frontend/README.md`](frontend/README.md), 제품 원칙은 [`CLAUDE.md`](CLAUDE.md)를
참조하세요.

## 대회 소개

**AI Builder Sprint 2026**은 부산대학교 **APPTIVE**가 주최하고, **Upstage**, 부산대학교 **Anchor 사업단** 및 부산대학교 **AI융합교육원**이 후원하는 해커톤입니다. 참가자들은 자유로운 기술 스택을 바탕으로 실제로 동작하는 서비스를 직접 코드로 구현합니다.

| 항목 | 내용 |
| --- | --- |
| 주제 | AI를 통해 인간다움을 더욱 잘 드러낼 수 있는 서비스 개발 |
| 팀 구성 | 2~4인 1팀 |
| 개발 방식 | 코드 기반 앱 개발 필수 (노코드/로우코드 단독 사용 불가) |

### 진행 흐름

1. **팀 단위 참가 신청** — 팀원 정보, 프로젝트 아이디어, 활용 예정 AI 기술·API 제출
2. **참가팀 선발** (20~50팀) — 아이디어 참신성·실현 가능성·AI 활용 계획 기반 서류 심사
3. **예선 개발 기간** (7.27 ~ 8.3, 약 1주일) — API 크레딧 발급, 아이디어 구체화 및 개발
4. **결과물 제출 및 1차 심사** — 데모 영상/배포 링크, 코드 저장소, 발표 자료, AI 활용 증빙 제출
5. **본선 발표 및 질의응답** (8.7) — 팀당 7분 발표 + 5분 Q&A, 심사 후 수상팀 확정

### 기술 스택 및 규칙

- 사용 API·모델은 자유이며, **Upstage API**(Solar LLM, Document Parse, Information Extract) 활용 시 심사 가점
- Claude, GPT, Gemini 등 타사 모델 병행 사용 가능 (제약 없음)
- 프레임워크/언어 자유 (Python, JavaScript, React, Flutter 등)
- 결과물은 데모 가능한 동작하는 앱 (웹앱, 모바일앱, CLI 도구 등 형태 무관)
- 코딩 에이전트(Claude Code, Codex 등) 활용 시 `.claude/`, `AGENTS.md` 등 관련 설정·지침 파일을 저장소에 포함해야 심사에 반영됩니다

### 심사 기준

| 기준 | 배점 |
| --- | --- |
| 창의성 | 20점 |
| AI 활용도 | 20점 |
| 완성도 | 20점 |
| 실용성 | 20점 |
| 발표력 (본선) | 20점 |
| Upstage API 활용 가점 | +5점 |
| 지역사회 기여도 가점 | +5점 |

### 시상 내역

- 대상 1팀: 100만원 + 상품
- 최우수상 1팀: 50만원 + 상품
- 우수상 1팀: 상품
- 본선 참가 10팀: Upstage 굿즈 + 참가 인증서

## Git Fork 하는 방법

참가팀은 이 저장소를 팀 대표의 GitHub 계정으로 **Fork**한 뒤, 해당 Fork 저장소에서 프로젝트를 개발하고 최종 결과물을 제출합니다.

### 1. 저장소 Fork하기

1. [AI-Builder-Sprint 저장소](https://github.com/ApptiveDev/AI-Builder-Sprint)에 접속합니다.
2. 우측 상단의 **Fork** 버튼을 클릭합니다.
  <img width="1888" height="1131" alt="스크린샷 2026-07-27 오전 12 31 16" src="https://github.com/user-attachments/assets/2f0f7f80-6c92-4ba5-87c5-89ed6107eeab" />

3. 본인(또는 팀 대표) GitHub 계정으로 저장소가 복사됩니다. (`https://github.com/<내-계정>/AI-Builder-Sprint`)

### 2. Fork한 저장소 로컬로 클론하기

```bash
git clone https://github.com/<내-계정>/AI-Builder-Sprint.git
cd AI-Builder-Sprint
```

### 3. 개발 진행 및 커밋

```bash
git checkout -b develop
# 코드 작성 및 수정
git add .
git commit -m "feat: 프로젝트 초기 구현"
git push origin develop
```

포크된 저장소 내에서 개발을 진행해주시면 됩니다.

### 4. 결과물 제출

- **팀별로 Fork한 본인 저장소 URL을 제출 양식에 기재합니다.**
- 제출 마감 전까지 코드, 데모 영상/배포 링크, 발표 자료를 함께 준비해 제출해주세요.
- 코딩 에이전트를 활용한 경우 `.claude/`, `AGENTS.md` 등 설정 파일도 반드시 저장소에 포함해주세요.


## 문의

- 대회 관련 문의: 해커톤 문의 오픈채팅방
- 주최: 부산대학교 APPTIVE, 정보컴퓨터공학부 동아리연합회 / 후원: Upstage, 부산대 Anchor 사업단, 부산대 AI융합교육원
