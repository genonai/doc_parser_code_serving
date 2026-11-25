"""글자 수 청킹(chunk_mode=character)의 분할 계산.

섹션 구조를 보지 않고 항목 텍스트를 읽기 순서대로 이어 붙여 chunk_size 글자까지 채워 자른다.
docling 타입을 import 하지 않는 순수 함수만 둔다. 항목 텍스트를 만드는 일과 DocChunk 조립은
청커(`smart_chunker._chunk_character`)가 맡는다.
"""

from __future__ import annotations

from typing import NamedTuple

# 자르는 위치를 앞당겨 찾는 범위. 조각 크기의 이 비율만큼 앞에서 줄바꿈 → 공백 순으로 찾는다.
BACKOFF_RATIO = 0.1


class CharSpan(NamedTuple):
    """조각 하나. text 는 overlap 을 포함한 본문이고 [own_s, own_e) 는 이 조각이 새로 시작한 구간이다.
    items 는 새로 시작한 구간과 겹치는 항목 index 목록이다(overlap 부분의 항목은 넣지 않는다)."""
    text: str
    own_s: int
    own_e: int
    items: list


def _cut_end(text: str, start: int, cap: int) -> int:
    """start 부터 cap 글자 안에서 자를 위치(끝, 미포함)를 고른다."""
    target = start + cap
    if target >= len(text):
        return len(text)
    lo = max(start + 1, target - max(1, int(cap * BACKOFF_RATIO)))
    for sep in ("\n", " "):
        pos = text.rfind(sep, lo - 1, target)
        if pos >= start:
            return pos + 1  # 구분 문자는 앞 조각 끝에 둔다
    return target


def _in_chunk(s: int, e: int, own_s: int, own_e: int, last: bool, total: int) -> bool:
    if e > s:
        return s < own_e and e > own_s
    return own_s <= s < own_e or (last and s == total)


def split_spans(texts: list, size: int, overlap: int = 0, delim: str = "\n") -> list:
    """항목 텍스트 목록을 size 글자 이하 조각으로 자른다.

    항목 구간에는 뒤따르는 delim 을 포함한다. 빈 텍스트 항목(설명 없는 그림 등)은 delim 없이
    길이 0 구간으로 두고, 그 위치를 포함하는 조각(문서 끝이면 마지막 조각)에 넣는다.
    size 가 0 이하이면 나누지 않는다. overlap 이 음수이거나 size 이상이면 0 으로 본다.
    """
    spans = []
    parts = []
    pos = 0
    prev = -1  # 마지막 비지 않은 항목 index
    for text in texts:
        if not text:
            spans.append((pos, pos))
            continue
        if parts:
            parts.append(delim)
            pos += len(delim)
            # 앞 항목 구간을 뒤따르는 delim 까지 늘린다.
            spans[prev] = (spans[prev][0], pos)
        prev = len(spans)
        spans.append((pos, pos + len(text)))
        parts.append(text)
        pos += len(text)
    full = "".join(parts)
    total = len(full)
    if not texts:
        return []
    if total == 0 or size <= 0:
        return [CharSpan(full, 0, total, list(range(len(texts))))]
    if not 0 <= overlap < size:
        overlap = 0

    result = []
    own_s = 0
    first = 0  # 항목 구간은 시작 위치 순이므로 앞에서 끝난 항목은 다시 보지 않는다
    while own_s < total:
        ov = min(overlap, own_s)
        own_e = _cut_end(full, own_s, size - ov)
        last = own_e >= total
        while first < len(spans) and not _in_chunk(*spans[first], own_s, own_e, last, total) \
                and spans[first][0] < own_s:
            first += 1
        items = []
        j = first
        while j < len(spans) and (spans[j][0] < own_e or last):
            if _in_chunk(*spans[j], own_s, own_e, last, total):
                items.append(j)
            j += 1
        result.append(CharSpan(full[own_s - ov:own_e], own_s, own_e, items))
        own_s = own_e
    return result


def table_piece_counts(chunk_items: list, table_indexes: set) -> dict:
    """표 항목 index -> 그 표를 담은 조각 수. 기록할 표만 돌려준다.

    조각 수가 2 이상이고, 그 조각들이 모두 표를 하나만 담을 때만 기록한다. 한 조각에 표가
    여럿이면 조각 순번이 성립하지 않는다(vector_meta 가 표 하나인 청크에서만 순번을 매긴다).
    """
    counts: dict = {}
    mixed: set = set()
    for items in chunk_items:
        tables = [i for i in items if i in table_indexes]
        for i in tables:
            counts[i] = counts.get(i, 0) + 1
            if len(tables) > 1:
                mixed.add(i)
    return {i: n for i, n in counts.items() if n >= 2 and i not in mixed}
