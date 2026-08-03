"""[8] 축적 뷰 시연용 이력 시드.

세션 1회만 보면 이 제품은 "선호 파악 도구"로만 보인다. 정작 핵심 가치는
반복에서 나온다:

    1회   → 선호      "고민 중인 줄 알았는데 사실 B에 마음이 가 있구나"
    반복  → 가치관    "나는 이런 걸 중요하게 여기는 사람이구나"
    3개월 → 확신      "내 직관은 믿을 만하구나"

그 두 번째·세 번째 층은 시간이 지나야만 생기므로 시연에서는 심어줄 수밖에 없다.

⚠️ 이건 **시연용 가짜 이력**이다. 실제 측정값이 아니다.
   모든 id 에 `seed-` 접두어를 붙이고 별도 user_id 로 심어 실제 기록과 섞이지 않게 한다.

★규모를 현실적으로 잡는다.
  작은 고민까지 다루므로("점심 뭐 먹지") 실제 사용은 주 3~4회다. 6개월이면 90건 안팎.
  9건짜리 이력으로는 축이 벌어지지도 않고 가치관이 변하는 것도 안 보인다.

★시간에 따라 기울기가 **변한다.**
  초반에는 안정을 택하다가 후반에 성장으로 옮겨간다. 처음부터 한 방향이면
  그건 가치관이 아니라 설정이다. 사람은 겪으면서 바뀐다.

사용법 (backend/ 에서):
    .venv/Scripts/python.exe scripts/seed_history.py          # 심기
    .venv/Scripts/python.exe scripts/seed_history.py --clear   # 지우기
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import storage  # noqa: E402
from app.schemas.analysis import (  # noqa: E402
    Lean,
    PreferenceVerdict,
    StateLabel,
    StateVerdict,
    Verdict,
)
from app.schemas.decision import Decision, Option  # noqa: E402
from app.schemas.report import Annotation  # noqa: E402
from app.schemas.session import Horizon, Retrospective, Session  # noqa: E402

PREFIX = "seed-"
NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
SPAN_DAYS = 183

DEMO_USER_ID = "demo-intuition-note"
"""이 이력의 주인.

프론트에서 `?user=demo-intuition-note` 로 열면 전환된다.
실제 사용자의 기록과는 user_id 로 완전히 분리되어 섞이지 않는다.
"""

RNG = random.Random(20260802)
"""고정 시드 — 시연 때마다 같은 이력이 나와야 설명이 흔들리지 않는다."""


class Axis:
    """한 가치 축과 그 축에 속하는 고민들.

    `drift` 는 시간에 따른 기울기 변화다. 0.0 이면 초반에도 후반에도 같은 비율로
    한쪽을 택하고, 1.0 이면 초반에는 극 A, 후반에는 극 B 로 완전히 옮겨간다.
    """

    def __init__(
        self,
        *,
        name: str,
        poles: tuple[str, str],
        weight: int,
        early_bias: float,
        late_bias: float,
        decisions: list[tuple[str, str, str]],
    ) -> None:
        self.name = name
        self.poles = poles
        self.weight = weight
        self.early_bias = early_bias  # 초반에 poles[1] 을 택할 확률
        self.late_bias = late_bias  # 후반에 poles[1] 을 택할 확률
        self.decisions = decisions  # (제목, 극0 라벨, 극1 라벨)


# 28세 개발자의 6개월. 반년 전 이직을 겪고 그 뒤 가치관이 옮겨가는 중이다.
AXES: list[Axis] = [
    Axis(
        name="안정 vs 성장",
        poles=("안정", "성장"),
        weight=18,
        early_bias=0.35,  # 처음엔 안정 쪽이 많았다
        late_bias=0.85,  # 지금은 성장 쪽으로 굳었다
        decisions=[
            ("지금 회사에 남을지 옮길지", "지금 회사에 남는다", "옮긴다"),
            ("대학원에 갈지 실무를 이어갈지", "실무를 이어간다", "대학원에 간다"),
            ("사이드 프로젝트를 시작할지", "당분간 쉰다", "사이드를 시작한다"),
            ("팀을 옮길지 남을지", "지금 팀에 남는다", "새 팀으로 옮긴다"),
            ("새 언어를 배울지 지금 걸 더 팔지", "지금 것을 더 판다", "새 언어를 배운다"),
            ("발표를 맡을지 넘길지", "다른 사람에게 넘긴다", "발표를 맡는다"),
            ("낯선 도메인 과제를 받을지", "익숙한 과제를 고른다", "낯선 과제를 받는다"),
            ("자격증을 딸지 실무에 쓸지", "실무 시간에 쓴다", "자격증을 딴다"),
            ("스터디를 만들지 말지", "혼자 공부한다", "스터디를 만든다"),
            ("연봉 협상을 할지 그냥 갈지", "그냥 간다", "협상한다"),
        ],
    ),
    Axis(
        name="관계 vs 자율",
        poles=("관계", "자율"),
        weight=15,
        early_bias=0.30,  # 초반엔 관계를 챙겼다
        late_bias=0.65,  # 점점 자기 시간 쪽으로
        decisions=[
            ("주말 모임에 나갈지 쉴지", "모임에 나간다", "혼자 쉰다"),
            ("이사할 때 어디로 갈지", "친구들 근처로 간다", "회사 근처로 간다"),
            ("가족 행사에 갈지", "가족 행사에 간다", "혼자 시간을 낸다"),
            ("동아리를 계속할지", "동아리를 계속한다", "그만둔다"),
            ("점심을 같이 먹을지", "같이 먹는다", "혼자 먹는다"),
            ("연락을 먼저 할지", "먼저 연락한다", "기다린다"),
            ("경조사에 갈지", "간다", "안 간다"),
            ("팀 회식에 남을지", "끝까지 남는다", "먼저 일어난다"),
        ],
    ),
    Axis(
        name="즉시 vs 유예",
        poles=("즉시", "유예"),
        weight=13,
        early_bias=0.55,
        late_bias=0.30,  # 미루는 게 줄었다
        decisions=[
            ("치과 예약을 오늘 잡을지", "오늘 잡는다", "다음에 잡는다"),
            ("이 기능 지금 만들지", "지금 만든다", "다음 스프린트로 미룬다"),
            ("회의를 지금 잡을지", "지금 잡는다", "다음 주로 미룬다"),
            ("설거지를 지금 할지", "지금 한다", "이따 한다"),
            ("메일에 지금 답할지", "지금 답한다", "내일 답한다"),
            ("리팩터링을 지금 할지", "지금 한다", "나중에 한다"),
            ("병원에 갈지 좀 더 볼지", "바로 간다", "며칠 지켜본다"),
        ],
    ),
    Axis(
        name="휴식 vs 집중",
        poles=("휴식", "집중"),
        weight=12,
        early_bias=0.60,
        late_bias=0.45,
        decisions=[
            ("지금 잘지 더 할지", "지금 잔다", "하던 일을 계속한다"),
            ("샤워를 할지 이어서 할지", "지금 샤워한다", "하던 일을 계속한다"),
            ("산책을 나갈지", "산책을 나간다", "자리에 앉아 있는다"),
            ("휴가를 쓸지 미룰지", "이번에 쓴다", "더 미룬다"),
            ("커피를 더 마실지", "그만 마신다", "한 잔 더 마신다"),
            ("주말에 일할지", "쉰다", "일한다"),
        ],
    ),
    Axis(
        name="절약 vs 투자",
        poles=("절약", "투자"),
        weight=9,
        early_bias=0.30,
        late_bias=0.60,
        decisions=[
            ("비싼 노트북을 살지", "싼 걸로 버틴다", "비싼 걸 산다"),
            ("유료 강의를 결제할지", "무료로 찾아본다", "결제한다"),
            ("의자를 바꿀지", "쓰던 걸 쓴다", "새로 산다"),
            ("택시를 탈지", "지하철을 탄다", "택시를 탄다"),
            ("구독을 유지할지", "해지한다", "유지한다"),
        ],
    ),
    Axis(
        name="익숙함 vs 새로움",
        poles=("익숙함", "새로움"),
        weight=8,
        early_bias=0.40,
        late_bias=0.70,
        decisions=[
            ("새 프레임워크를 배울지", "지금 쓰는 걸 더 판다", "새 프레임워크를 배운다"),
            ("가던 식당에 갈지", "가던 곳에 간다", "새 곳에 간다"),
            ("여행지를 다시 갈지", "가봤던 곳에 간다", "안 가본 곳에 간다"),
            ("에디터를 바꿀지", "쓰던 걸 쓴다", "바꾼다"),
        ],
    ),
    Axis(
        name="정직 vs 배려",
        poles=("정직", "배려"),
        weight=6,
        early_bias=0.45,
        late_bias=0.55,
        decisions=[
            ("부모님께 사실대로 말할지", "사실대로 말한다", "말하지 않는다"),
            ("부당한 일에 문제를 제기할지", "문제를 제기한다", "넘어간다"),
            ("코드 리뷰에서 세게 말할지", "그대로 말한다", "부드럽게 넘긴다"),
            ("선물이 마음에 안 든다고 할지", "말한다", "고맙다고만 한다"),
        ],
    ),
    Axis(
        name="몰입 vs 균형",
        poles=("몰입", "균형"),
        weight=5,
        early_bias=0.60,
        late_bias=0.40,
        decisions=[
            ("야근을 더 할지", "끝까지 한다", "내일 한다"),
            ("주말에도 코드를 볼지", "본다", "안 본다"),
            ("이 프로젝트에 더 걸지", "더 건다", "적당히 한다"),
        ],
    ),
    Axis(
        name="공유 vs 보호",
        poles=("공유", "보호"),
        weight=4,
        early_bias=0.50,
        late_bias=0.60,
        decisions=[
            ("블로그 글을 공개할지", "공개한다", "비공개로 둔다"),
            ("사이드 코드를 오픈할지", "오픈한다", "비공개로 둔다"),
            ("고민을 팀에 말할지", "말한다", "혼자 안고 간다"),
        ],
    ),
    Axis(
        name="책임 vs 자유",
        poles=("책임", "자유"),
        weight=3,
        early_bias=0.40,
        late_bias=0.50,
        decisions=[
            ("고양이를 입양할지", "입양한다", "지금은 안 한다"),
            ("스터디 리더를 맡을지", "맡는다", "안 맡는다"),
        ],
    ),
    # 한 번씩만 나온 축들 — 실제 이력에는 이런 꼬리가 반드시 있다
    Axis(
        name="유동성 vs 목돈",
        poles=("유동성", "목돈"),
        weight=2,
        early_bias=0.5,
        late_bias=0.5,
        decisions=[("월세로 갈지 전세로 갈지", "월세로 간다", "전세로 간다")],
    ),
    Axis(
        name="수익 vs 정리",
        poles=("수익", "정리"),
        weight=2,
        early_bias=0.5,
        late_bias=0.5,
        decisions=[("중고로 팔지 버릴지", "중고로 판다", "그냥 버린다")],
    ),
    Axis(
        name="집중 vs 분산",
        poles=("집중", "분산"),
        weight=2,
        early_bias=0.5,
        late_bias=0.5,
        decisions=[("휴가를 몰아 쓸지", "몰아 쓴다", "나눠 쓴다")],
    ),
]

BODY_TAGS = [
    "가슴 답답함", "손끝 떨림", "설렘", "이유 없는 찜찜함",
    "몸이 가벼움", "목이 조임", "아무 느낌 없음",
]

SELF_NOTES = [
    "말하면서 알았는데 이미 그쪽으로 기울어 있었네요",
    "머리로는 반대인데 목소리가 달랐어요",
    "이번엔 망설임이 별로 없었어요",
    "둘 다 비슷하게 나왔는데 말하고 나니 알겠어요",
    "생각보다 뚜렷하게 나와서 놀랐어요",
    "아직도 잘 모르겠는데 조금은 보이네요",
    "몸이 먼저 답을 알고 있었던 것 같아요",
    "",
]

RETRO_NOTES_GOOD = [
    "그렇게 하길 잘했어요",
    "힘든데 후회는 없어요",
    "지금 보면 맞는 선택이었어요",
    "그때 그 느낌이 맞았네요",
]
RETRO_NOTES_BAD = [
    "계속 미련이 남아요",
    "그때 다르게 할 걸 그랬어요",
    "내내 마음이 안 편했어요",
    "지금 생각하면 아쉬워요",
]

# 지평별 최소 경과일 — 9일 전 기록에 3개월 회고가 있을 수는 없다
HORIZON_DAYS = {Horizon.W1: 7, Horizon.M3: 90, Horizon.M6: 180}


def _bias_at(axis: Axis, days_ago: int) -> float:
    """시간에 따라 기울기가 옮겨간다. days_ago 가 클수록 초반."""
    progress = 1.0 - (days_ago / SPAN_DAYS)  # 0=가장 오래전, 1=오늘
    return axis.early_bias + (axis.late_bias - axis.early_bias) * progress


def _plan() -> list[tuple[int, Axis, tuple[str, str, str]]]:
    """(며칠 전, 축, 고민) 목록. 축 가중치에 비례해 뽑고 날짜를 흩뿌린다.

    ★섞는 것이 핵심이다. 축별로 뭉친 채 날짜를 붙이면 한 축이 특정 시기를
    독점해서, 시간에 따른 기울기 변화(`_bias_at`)가 통째로 사라진다.
    사람은 여러 축의 고민을 섞어서 겪는다.
    """
    slots: list[tuple[Axis, tuple[str, str, str]]] = []
    for axis in AXES:
        for i in range(axis.weight):
            slots.append((axis, axis.decisions[i % len(axis.decisions)]))
    RNG.shuffle(slots)

    days = sorted(RNG.sample(range(2, SPAN_DAYS), len(slots)), reverse=True)
    return [(day, axis, decision) for day, (axis, decision) in zip(days, slots)]


def _build(index: int, days_ago: int, axis: Axis, spec: tuple[str, str, str]):
    title, label_0, label_1 = spec
    created = NOW - timedelta(days=days_ago)
    key = f"{index:03d}"

    decision = Decision(
        id=f"{PREFIX}d{key}",
        user_id=DEMO_USER_ID,
        raw_input=title,
        title=title,
        value_axis=axis.name,
        options=[
            Option(
                id=f"{PREFIX}o{key}-{i}",
                label=label,
                axis_side=pole,
                imagine_prompt=(
                    f"'{label}'을 선택한 뒤의 한 장면을 떠올려보세요. "
                    "무엇이 보이고 무엇이 느껴지나요?"
                ),
                speak_prompt="방금 그 장면에서 든 느낌을 그대로 말해주세요.",
                order_index=i,
            )
            for i, (label, pole) in enumerate(zip((label_0, label_1), axis.poles))
        ],
        created_at=created,
    )

    # 자기 진술 — 시간에 따라 기울기가 옮겨간다
    lean_to_1 = RNG.random() < _bias_at(axis, days_ago)
    self_lean = 1 if lean_to_1 else 0
    # 열에 하나쯤은 "아직 모르겠어요"
    undecided = RNG.random() < 0.10

    session_id = f"{PREFIX}s{key}"
    # 우리 판정은 자기 진술과 4번에 1번쯤 어긋난다 — 그 어긋남이 [8]의 재료다
    verdict_lean = self_lean if RNG.random() > 0.25 else 1 - self_lean
    state = RNG.choice([StateLabel.CALM, StateLabel.CALM, StateLabel.AROUSED, StateLabel.FLAT])

    session = Session(
        id=session_id,
        user_id=DEMO_USER_ID,
        decision_id=decision.id,
        verdict=Verdict(
            session_id=session_id,
            preference=PreferenceVerdict(
                lean=Lean.A if verdict_lean == 0 else Lean.B,
                lean_option_id=decision.options[verdict_lean].id,
                magnitude=round(RNG.uniform(0.10, 0.45), 3),
                confidence=round(RNG.uniform(0.30, 0.80), 3),
                contributing={},
            ),
            state=StateVerdict(label=state, magnitude=round(RNG.uniform(0.05, 0.35), 3)),
        ),
        annotation=Annotation(
            session_id=session_id,
            option_id=decision.options[self_lean].id,
            body_tags=RNG.sample(BODY_TAGS, RNG.choice([0, 1, 1, 2])),
            self_lean_option_id=None if undecided else decision.options[self_lean].id,
            self_lean_note=RNG.choice(SELF_NOTES) or None,
        ),
        created_at=created,
    )

    # 회고 — 지평이 지난 것만, 그중 절반쯤만 실제로 답한다
    retro = None
    available = [h for h, need in HORIZON_DAYS.items() if days_ago >= need]
    if available and not undecided and RNG.random() < 0.55:
        horizon = available[-1]
        followed = RNG.random() < 0.70  # 대개 자기 진술대로 고른다
        chosen = self_lean if followed else 1 - self_lean
        satisfaction = (
            RNG.choice([3, 4, 4, 5, 5]) if followed else RNG.choice([1, 2, 2, 3, 4])
        )
        retro = Retrospective(
            session_id=session_id,
            horizon=horizon,
            chosen_option_id=decision.options[chosen].id,
            satisfaction=satisfaction,
            note=RNG.choice(RETRO_NOTES_GOOD if satisfaction >= 4 else RETRO_NOTES_BAD),
            created_at=created + timedelta(days=HORIZON_DAYS[horizon]),
        )
    return decision, session, retro


def seed() -> None:
    storage.init_db()
    plan = _plan()
    retro_count = 0
    for index, (days_ago, axis, spec) in enumerate(plan, start=1):
        decision, session, retro = _build(index, days_ago, axis, spec)
        storage.put(
            "decisions", decision.id, decision.model_dump(mode="json"), user_id=DEMO_USER_ID
        )
        storage.put(
            "sessions",
            session.id,
            session.model_dump(mode="json"),
            decision_id=decision.id,
            user_id=DEMO_USER_ID,
        )
        if retro is not None:
            storage.put_retrospective(
                session.id, retro.horizon.value, retro.model_dump(mode="json")
            )
            retro_count += 1

    print(f"심었습니다 — 고민 {len(plan)}건, 회고 {retro_count}건, 축 {len(AXES)}개")
    print(f"기간: 최근 {SPAN_DAYS}일   사용자: {DEMO_USER_ID}")
    print()
    print(f"시연:   http://localhost:5173/?user={DEMO_USER_ID}")
    print(f"확인:   curl -H 'X-User-Id: {DEMO_USER_ID}' http://127.0.0.1:8000/value-map")
    print()
    print("주의  심어둔 이력은 실제 측정이 아니다. 시연에서 반드시 밝힐 것.")


def clear() -> None:
    with storage.connect() as conn:
        retros = conn.execute(
            "DELETE FROM retrospectives WHERE session_id LIKE ?", (f"{PREFIX}%",)
        ).rowcount
        sessions = conn.execute(
            "DELETE FROM sessions WHERE id LIKE ?", (f"{PREFIX}%",)
        ).rowcount
        decisions = conn.execute(
            "DELETE FROM decisions WHERE id LIKE ?", (f"{PREFIX}%",)
        ).rowcount
    print(f"지웠습니다 — 고민 {decisions}건, 세션 {sessions}건, 회고 {retros}건")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        clear()
    else:
        seed()
