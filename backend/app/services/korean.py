"""한국어 조사 선택.

선택지 이름은 사용자가 방금 입력한 말에서 나오므로 무엇이 올지 알 수 없다.
'을(를)'처럼 둘 다 적어두면 읽는 순간 기계가 쓴 문장이 되고, 자기 고민을
비추는 거울이라는 느낌이 깨진다.
"""

from __future__ import annotations

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3
_JONGSEONG_COUNT = 28

# 앞 글자가 숫자로 끝날 때의 받침 유무. '1'은 '일'이라 받침이 있다.
_DIGIT_HAS_FINAL = {
    "0": True,   # 영
    "1": True,   # 일
    "3": True,   # 삼
    "6": True,   # 육
    "7": True,   # 칠
    "8": True,   # 팔
    "2": False,  # 이
    "4": False,  # 사
    "5": False,  # 오
    "9": False,  # 구
}


def has_final_consonant(word: str) -> bool | None:
    """마지막 글자에 받침이 있는가. 판단할 수 없으면 None."""
    stripped = word.strip().rstrip("'\"’”)]》」")
    if not stripped:
        return None

    last = stripped[-1]
    if last in _DIGIT_HAS_FINAL:
        return _DIGIT_HAS_FINAL[last]

    code = ord(last)
    if not (_HANGUL_START <= code <= _HANGUL_END):
        # 한글도 숫자도 아니면(영문·기호) 알 수 없다.
        return None
    return (code - _HANGUL_START) % _JONGSEONG_COUNT != 0


def josa(word: str, pair: str) -> str:
    """받침 유무로 조사를 고른다.

    >>> josa("이직", "을/를")
    '을'
    >>> josa("퇴사", "을/를")
    '를'

    `pair`는 '받침있음/받침없음' 순서다 ('을/를', '이/가', '은/는', '과/와').
    판단할 수 없으면 둘 다 적어 안전하게 넘긴다 — 틀린 조사보다 낫다.
    """
    with_final, without_final = pair.split("/")
    final = has_final_consonant(word)
    if final is None:
        return f"{with_final}({without_final})"
    return with_final if final else without_final


def with_josa(word: str, pair: str) -> str:
    """단어에 조사를 붙여 돌려준다. '이직' + '을/를' → '이직을'."""
    return f"{word}{josa(word, pair)}"
