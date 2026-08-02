"""한국어 조사 선택.

선택지 이름은 사용자가 방금 입력한 말에서 나오므로 무엇이 올지 알 수 없다.
'을(를)'로 적어두면 읽는 순간 기계가 쓴 문장이 되고, 자기 고민을 비추는
거울이라는 느낌이 깨진다.
"""

from __future__ import annotations

import pytest

from app.services.korean import has_final_consonant, josa, with_josa


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("이직", "을"),  # ㄱ 받침
        ("퇴사", "를"),
        ("남는다", "를"),
        ("창업", "을"),  # ㅂ 받침
        ("유학", "을"),
        ("서울", "을"),  # ㄹ 받침도 받침이다
    ],
)
def test_object_particle(word: str, expected: str) -> None:
    assert josa(word, "을/를") == expected


@pytest.mark.parametrize(
    ("word", "pair", "expected"),
    [
        ("목소리 높이", "이/가", "가"),
        ("말속도", "이/가", "가"),
        ("심박수", "이/가", "가"),
        ("말 사이 쉼", "이/가", "이"),
        ("이직", "은/는", "은"),
        ("퇴사", "은/는", "는"),
    ],
)
def test_other_particles(word: str, pair: str, expected: str) -> None:
    assert josa(word, pair) == expected


@pytest.mark.parametrize(
    ("word", "expected"),
    [("1", "을"), ("2", "를"), ("3", "을"), ("4", "를"), ("6", "을"), ("9", "를")],
)
def test_digits_use_their_reading(word: str, expected: str) -> None:
    """'1'은 '일'이라 받침이 있고 '2'는 '이'라 없다. 선택지가 숫자로 끝날 수 있다."""
    assert josa(word, "을/를") == expected


def test_unknown_ending_keeps_both_forms() -> None:
    """영문·기호로 끝나면 판단할 수 없다. 틀린 조사보다 둘 다 적는 게 낫다."""
    assert josa("startup", "을/를") == "을(를)"
    assert josa("...", "이/가") == "이(가)"


def test_trailing_quotes_are_ignored() -> None:
    """리포트가 선택지를 따옴표로 감싸므로 그 안쪽 글자를 봐야 한다."""
    assert has_final_consonant("이직'") is True
    assert has_final_consonant("퇴사'") is False


def test_empty_input_is_undecidable() -> None:
    assert has_final_consonant("") is None
    assert has_final_consonant("   ") is None


def test_with_josa_attaches() -> None:
    assert with_josa("이직", "을/를") == "이직을"
    assert with_josa("퇴사", "을/를") == "퇴사를"
