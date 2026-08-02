"""[8] 축적 뷰 데모용 이력 시드.

세션 1회만 보면 이 제품은 "선호 파악 도구"로만 보인다. 정작 핵심 가치는
반복에서 나온다:

    1회   → 선호      "고민 중인 줄 알았는데 사실 B에 마음이 가 있구나"
    반복  → 가치관    "나는 이런 걸 중요하게 여기는 사람이구나"
    3개월 → 확신      "내 직관은 믿을 만하구나"

그 두 번째·세 번째 층은 시간이 지나야만 생기므로, 데모에서는 심어줄 수밖에 없다.

⚠️ 이건 **데모용 가짜 이력**이다. 실제 측정값이 아니다.
   모든 id에 `seed-` 접두어를 붙여 실제 기록과 구분하고 언제든 지울 수 있게 한다.

사용법 (backend/ 에서):
    .venv/Scripts/python.exe scripts/seed_history.py          # 심기
    .venv/Scripts/python.exe scripts/seed_history.py --clear   # 지우기
"""

from __future__ import annotations

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

DEMO_USER_ID = "demo-intuition-note"
"""이 이력의 주인.

축적 뷰(2층 가치관 / 3층 확신)는 여러 달치 이력이 있어야 뜻이 생기는데, 시연
자리에서 그걸 만들 수는 없다. 미리 심어둔 이 사용자로 갈아타면 바로 보여줄 수 있다.

프론트에서 `?user=demo-intuition-note` 로 열면 전환된다.
실제 사용자의 기록과는 `user_id` 로 완전히 분리되어 섞이지 않는다.
"""


class Entry:
    """한 건의 과거 기록. 선택지 두 개와 그때 사용자가 말한 것."""

    def __init__(
        self,
        *,
        key: str,
        days_ago: int,
        title: str,
        raw_input: str,
        value_axis: str,
        labels: tuple[str, str],
        sides: tuple[str, str],
        # 사용자가 자기 입으로 말한 쪽 (0 또는 1). ★이 제품의 핵심 산출물
        self_lean: int,
        # 우리 내부 판정. 자기 진술과 어긋날 수 있고, 그 어긋남이 곧 재료다
        verdict_lean: int | None,
        state: StateLabel,
        body_tags: list[str],
        self_lean_note: str,
        # 회고: (지평, 실제로 고른 쪽, 만족도 1~5, 메모)
        retro: tuple[Horizon, int, int, str] | None = None,
    ) -> None:
        self.key = key
        self.days_ago = days_ago
        self.title = title
        self.raw_input = raw_input
        self.value_axis = value_axis
        self.labels = labels
        self.sides = sides
        self.self_lean = self_lean
        self.verdict_lean = verdict_lean
        self.state = state
        self.body_tags = body_tags
        self.self_lean_note = self_lean_note
        self.retro = retro


# 6개월간 한 사람의 이력.
#
# "안정 vs 성장"은 5번 반복되며 성장 쪽으로 굳어진다 → 가치관이 드러나는 축.
# "관계 vs 자율"은 3번인데 갈린다 → 아직 형성 중인 축. 셋 다 한 방향이면
# 데이터가 아니라 우화가 된다.
ENTRIES: list[Entry] = [
    Entry(
        key="1",
        days_ago=181,
        title="지금 회사에 남을지 스타트업으로 옮길지",
        raw_input="지금 회사에 남을지 스타트업으로 옮길지 고민이야",
        value_axis="안정 vs 성장",
        labels=("지금 회사에 남는다", "스타트업으로 옮긴다"),
        sides=("안정", "성장"),
        self_lean=1,
        verdict_lean=1,
        state=StateLabel.AROUSED,
        body_tags=["가슴 답답함", "설렘"],
        self_lean_note="말하면서 알았는데 이미 옮기는 쪽으로 기울어 있었네요",
        retro=(Horizon.M3, 1, 5, "옮기길 잘했어요. 힘든데 살아 있는 느낌이에요"),
    ),
    Entry(
        key="2",
        days_ago=166,
        title="주말 모임에 나갈지 혼자 쉴지",
        raw_input="주말 모임 나갈지 그냥 혼자 쉴지",
        value_axis="관계 vs 자율",
        labels=("모임에 나간다", "혼자 쉰다"),
        sides=("관계", "자율"),
        self_lean=1,
        verdict_lean=1,
        state=StateLabel.FLAT,
        body_tags=["몸이 가벼움"],
        self_lean_note="쉬고 싶다는 게 이렇게 뚜렷할 줄 몰랐어요",
        retro=(Horizon.W1, 1, 4, "쉬길 잘했어요"),
    ),
    Entry(
        key="3",
        days_ago=142,
        title="대학원에 갈지 실무를 이어갈지",
        raw_input="대학원 갈지 그냥 계속 일할지",
        value_axis="안정 vs 성장",
        labels=("실무를 이어간다", "대학원에 간다"),
        sides=("안정", "성장"),
        self_lean=1,
        verdict_lean=0,
        state=StateLabel.CALM,
        body_tags=["이유 없는 찜찜함"],
        self_lean_note="머리로는 실무가 낫다는데 자꾸 대학원 얘기할 때 목소리가 커지더라고요",
        retro=(Horizon.M3, 0, 2, "결국 실무를 택했는데 계속 미련이 남아요"),
    ),
    Entry(
        key="4",
        days_ago=118,
        title="이사할 때 회사 근처로 갈지 친구들 근처로 갈지",
        raw_input="이사 회사 근처로 갈지 친구들 사는 동네로 갈지",
        value_axis="관계 vs 자율",
        labels=("친구들 근처로 간다", "회사 근처로 간다"),
        sides=("관계", "자율"),
        self_lean=0,
        verdict_lean=0,
        state=StateLabel.CALM,
        body_tags=["설렘"],
        self_lean_note="친구들 얘기할 때 말이 빨라지는 게 스스로도 들렸어요",
        retro=(Horizon.M3, 0, 4, "출퇴근은 길어졌지만 후회는 없어요"),
    ),
    Entry(
        key="5",
        days_ago=95,
        title="사이드 프로젝트를 시작할지 쉴지",
        raw_input="사이드 프로젝트 시작할지 그냥 좀 쉴지",
        value_axis="안정 vs 성장",
        labels=("당분간 쉰다", "사이드를 시작한다"),
        sides=("안정", "성장"),
        self_lean=1,
        verdict_lean=1,
        state=StateLabel.AROUSED,
        body_tags=["설렘", "손끝 떨림"],
        self_lean_note="쉬어야 한다고 생각했는데 시작하는 쪽이 더 편하게 나왔어요",
        retro=(Horizon.M3, 1, 4, "체력은 힘든데 시작한 건 잘한 것 같아요"),
    ),
    Entry(
        key="6",
        days_ago=71,
        title="팀을 옮길지 지금 팀에 남을지",
        raw_input="새 팀으로 옮길지 지금 팀에 남을지",
        value_axis="안정 vs 성장",
        labels=("지금 팀에 남는다", "새 팀으로 옮긴다"),
        sides=("안정", "성장"),
        self_lean=1,
        verdict_lean=1,
        state=StateLabel.CALM,
        body_tags=["몸이 가벼움"],
        self_lean_note="이번엔 망설임이 별로 없었어요",
        retro=(Horizon.M3, 1, 5, "옮긴 팀이 훨씬 맞아요"),
    ),
    Entry(
        key="7",
        days_ago=48,
        title="장기 여행을 갈지 돈을 모을지",
        raw_input="장기 여행 갈지 그 돈 모을지",
        value_axis="당장 vs 나중",
        labels=("지금 여행을 간다", "돈을 모아둔다"),
        sides=("당장", "나중"),
        self_lean=0,
        verdict_lean=None,
        state=StateLabel.AROUSED,
        body_tags=["설렘", "가슴 답답함"],
        self_lean_note="둘 다 비슷하게 나왔는데 말하고 나니 여행 쪽이더라고요",
        retro=(Horizon.W1, 0, 4, "예약했어요"),
    ),
    Entry(
        key="8",
        days_ago=27,
        title="가족 행사에 갈지 혼자 시간을 낼지",
        raw_input="이번 주말 가족 행사 갈지 혼자 시간 보낼지",
        value_axis="관계 vs 자율",
        labels=("가족 행사에 간다", "혼자 시간을 낸다"),
        sides=("관계", "자율"),
        self_lean=0,
        verdict_lean=1,
        state=StateLabel.FLAT,
        body_tags=["목이 조임"],
        self_lean_note="가야 한다고 말은 했는데 몸은 다른 얘기를 하는 것 같았어요",
        retro=(Horizon.W1, 0, 2, "가긴 갔는데 내내 지쳐 있었어요"),
    ),
    Entry(
        key="9",
        days_ago=9,
        title="새 언어를 배울지 지금 걸 더 팔지",
        raw_input="새 언어 배울지 지금 쓰는 걸 더 깊게 팔지",
        value_axis="안정 vs 성장",
        labels=("지금 것을 더 판다", "새 언어를 배운다"),
        sides=("안정", "성장"),
        self_lean=1,
        verdict_lean=1,
        state=StateLabel.CALM,
        body_tags=["설렘"],
        self_lean_note="이제 이런 건 금방 알겠어요",
        retro=None,  # 아직 회고 전 — 최근 기록이라 당연하다
    ),
]


def _decision(entry: Entry) -> Decision:
    created = NOW - timedelta(days=entry.days_ago)
    return Decision(
        id=f"{PREFIX}d{entry.key}",
        user_id=DEMO_USER_ID,
        raw_input=entry.raw_input,
        title=entry.title,
        value_axis=entry.value_axis,
        options=[
            Option(
                id=f"{PREFIX}o{entry.key}-{i}",
                label=label,
                axis_side=side,
                imagine_prompt=f"'{label}'을 선택한 6개월 뒤의 당신을 상상해보세요.",
                speak_prompt="방금 그 장면에서 든 느낌을 그대로 말해주세요.",
                order_index=i,
            )
            for i, (label, side) in enumerate(zip(entry.labels, entry.sides))
        ],
        created_at=created,
    )


def _session(entry: Entry, decision: Decision) -> Session:
    created = NOW - timedelta(days=entry.days_ago)
    session_id = f"{PREFIX}s{entry.key}"

    verdict = None
    if entry.verdict_lean is not None:
        verdict = Verdict(
            session_id=session_id,
            preference=PreferenceVerdict(
                lean=Lean.A if entry.verdict_lean == 0 else Lean.B,
                lean_option_id=decision.options[entry.verdict_lean].id,
                magnitude=0.24,
                confidence=0.55,
                contributing={},
            ),
            state=StateVerdict(label=entry.state, magnitude=0.18),
        )

    return Session(
        id=session_id,
        user_id=DEMO_USER_ID,
        decision_id=decision.id,
        # captures/features 는 비워둔다. 원자료를 영구 보관하지 않는다는
        # 프라이버시 전제와도 맞고, 축적 뷰에는 필요하지 않다.
        verdict=verdict,
        annotation=Annotation(
            session_id=session_id,
            option_id=decision.options[entry.self_lean].id,
            body_tags=entry.body_tags,
            self_lean_option_id=decision.options[entry.self_lean].id,
            self_lean_note=entry.self_lean_note,
        ),
        created_at=created,
    )


def seed() -> None:
    storage.init_db()
    for entry in ENTRIES:
        decision = _decision(entry)
        session = _session(entry, decision)
        storage.put(
            "decisions",
            decision.id,
            decision.model_dump(mode="json"),
            user_id=DEMO_USER_ID,
        )
        storage.put(
            "sessions",
            session.id,
            session.model_dump(mode="json"),
            decision_id=decision.id,
            user_id=DEMO_USER_ID,
        )
        if entry.retro is None:
            continue
        horizon, chosen, satisfaction, note = entry.retro
        retro = Retrospective(
            session_id=session.id,
            horizon=horizon,
            chosen_option_id=decision.options[chosen].id,
            satisfaction=satisfaction,
            note=note,
            created_at=session.created_at + _horizon_delta(horizon),
        )
        storage.put_retrospective(session.id, horizon.value, retro.model_dump(mode="json"))

    retros = sum(1 for e in ENTRIES if e.retro)
    print(f"심었습니다 — 고민 {len(ENTRIES)}건, 세션 {len(ENTRIES)}건, 회고 {retros}건")
    print(f"사용자: {DEMO_USER_ID}")
    print()
    print("시연:   http://localhost:5173/?user=" + DEMO_USER_ID)
    print("확인:   curl -H 'X-User-Id: %s' http://127.0.0.1:8000/value-map" % DEMO_USER_ID)
    print()
    print("⚠️  심어둔 이력은 실제 측정이 아니다. 시연에서 반드시 밝힐 것.")


def _horizon_delta(horizon: Horizon) -> timedelta:
    return {
        Horizon.W1: timedelta(days=7),
        Horizon.M3: timedelta(days=90),
        Horizon.M6: timedelta(days=180),
        Horizon.Y1: timedelta(days=365),
    }[horizon]


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
