"""구분자로 나뉜 텍스트 원천을 레코드 목록으로 읽는다.

## 왜 필요한가

원천이 항상 표준 포맷으로 오지는 않는다. 헤더 없이 데이터부터 시작하고, 필드를
`|@|` 처럼 **여러 글자로 된 구분자**로 나누며, 마지막 필드에 개행이 든 HTML 이
큰따옴표로 인용돼 들어오는 형태가 있다(모니모 고객센터 화재 원천).

파이썬 표준 `csv` 모듈은 구분자를 1문자로만 받아 이런 원천을 읽지 못한다. 확장자마다
로더를 늘리는 대신, "이 원천은 무엇으로 나뉘고 각 자리가 무슨 이름인가" 를 설정으로
받아 레코드 목록을 만든다.

산출은 `list[dict]` 라 `kind: records` 매핑이 그대로 소비한다 — 새 element category 나
새 매퍼를 만들지 않는다. `records_at` 도 필요 없다(`collect_records` 가 목록을 직접 받는다).

## 레코드 경계

**다음 레코드의 첫 줄**이 경계를 정한다. 구분자가 필드 수만큼 든 줄이 새 레코드의
시작이고, 그 밖의 줄은 마지막 필드 안의 개행으로 보고 직전 레코드에 이어 붙인다.

인용부호 개수로는 경계를 정하지 않는다. 본문 안 따옴표를 `""` 로 적지 않은 원천이 있어,
본문의 인용부호 한 개에서 레코드가 끝난 것으로 판정되어 뒷부분이 버려졌다(#782).
대신 본문 한 줄에 구분자가 필드 수만큼 들어 있으면 그 줄에서 레코드가 갈린다.

파일을 통째로 메모리에 올리지 않고 줄 단위로 흘린다 — 원천이 수백 MB 다.

docling 타입에 의존하지 않는다(텍스트 처리만 한다).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

_log = logging.getLogger(__name__)

# 인코딩을 지정하지 않았을 때 순서대로 시도한다. 국내 원천은 utf-8 아니면 cp949 다.
_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")

_CONFIG_KEY = "delimited"


@dataclass(frozen=True)
class DelimitedSpec:
    """`source.pre.delimited` 한 벌."""

    separator: str
    columns: tuple[str, ...]
    quote: str = '"'
    encoding: str | None = None
    skip_header: bool = False


def parse_spec(cfg: Any) -> DelimitedSpec | None:
    """설정 블록 → DelimitedSpec. 블록이 없으면 None.

    값이 잘못되면 기동 때 알려 준다 — 요청 때 원천을 읽다 실패하면 원인을 찾기 어렵다.
    """
    if cfg is None:
        return None
    if not isinstance(cfg, Mapping):
        raise ValueError(f"{_CONFIG_KEY} 형식 오류: 매핑 필요, 받은 형={type(cfg).__name__}")

    separator = str(cfg.get("separator") or "")
    if not separator:
        raise ValueError(f"{_CONFIG_KEY}.separator 비어 있음")

    raw_columns = cfg.get("columns")
    if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, str):
        raise ValueError(f"{_CONFIG_KEY}.columns 형식 오류: 이름 목록 필요")
    columns = tuple(str(name).strip() for name in raw_columns)
    if not columns or any(not name for name in columns):
        raise ValueError(f"{_CONFIG_KEY}.columns 에 빈 이름 있음")
    if len(set(columns)) != len(columns):
        raise ValueError(f"{_CONFIG_KEY}.columns 에 중복 이름 있음: {columns}")

    quote = str(cfg.get("quote") or '"')
    if len(quote) != 1:
        raise ValueError(f"{_CONFIG_KEY}.quote 값 오류: 1글자 필요, quote={quote!r}")

    encoding = cfg.get("encoding")
    return DelimitedSpec(
        separator=separator,
        columns=columns,
        quote=quote,
        encoding=str(encoding) if encoding else None,
        skip_header=bool(cfg.get("skip_header") or False),
    )


def _open_text(path: str, encoding: str | None):
    """인코딩을 정했으면 그것으로, 아니면 후보를 순서대로 시도한다."""
    candidates = (encoding,) if encoding else _ENCODINGS
    last: Exception | None = None
    for enc in candidates:
        try:
            handle = open(path, "r", encoding=enc, newline="")
            handle.readline()          # 앞부분만 읽어 디코딩 가능 여부를 본다
            handle.seek(0)
            return handle
        except UnicodeDecodeError as exc:
            last = exc
            continue
    # 후보가 모두 실패하면 마지막 후보로 손실을 감수하고 연다 — 본문 일부가 깨져도
    # 적재가 통째로 멈추는 것보다 낫고, 어느 인코딩도 못 읽는다는 사실은 로그로 남는다.
    _log.warning(f"[delimited] 인코딩 판정 실패, {candidates[-1]} 로 읽고 깨진 문자는 대체 문자로 처리: {last}")
    return open(path, "r", encoding=candidates[-1], errors="replace", newline="")


def _unquote(field: str, quote: str) -> str:
    if not field.startswith(quote):
        return field
    body = field[1:]
    if body.endswith(quote):
        body = body[:-1]
    return body.replace(quote * 2, quote)


def _to_record(parts: list[str], spec: DelimitedSpec) -> dict[str, str]:
    values = [*parts[:-1], _unquote(parts[-1], spec.quote)]
    return dict(zip(spec.columns, values))


def iter_records(path: str, spec: DelimitedSpec) -> Iterator[dict[str, str]]:
    """원천을 줄 단위로 흘리며 레코드를 뽑는다.

    필드 수는 `columns` 가 정한다. 구분자를 그 개수만큼만 쪼개므로 마지막 필드(본문) 안에
    구분자가 들어 있어도 잘리지 않는다.

    이어지는 줄은 조각 목록에 모았다가 마지막에 한 번만 합친다. 줄마다 문자열을 이어
    붙이고 다시 쪼개면 레코드 길이의 제곱에 비례하는 비용이 든다 — 본문이 수백 줄인
    원천에서는 그 차이가 크다(실측: 200MB·32,787건 기준 167초 → 1.5초).

    레코드는 다음 레코드의 첫 줄을 만나거나 파일이 끝날 때 내보낸다. 끝에 붙은 빈 줄은
    레코드 사이의 빈 줄이므로 버린다 — 남기면 닫는 인용부호 뒤에 개행이 붙어 `_unquote` 가
    인용부호를 떼지 못한다.
    """
    limit = len(spec.columns) - 1
    head: list[str] | None = None      # 첫 줄에서 확정한 앞 필드들
    chunks: list[str] = []             # 마지막 필드에 이어 붙일 조각들
    skipped = not spec.skip_header

    def finish(head: list[str]) -> dict[str, str] | None:
        nonlocal skipped
        while len(chunks) > 1 and not chunks[-1].strip():
            chunks.pop()
        if not skipped:
            skipped = True                         # 헤더 행 1건만 버린다
            return None
        return _to_record([*head, "\n".join(chunks)], spec)

    with _open_text(path, spec.encoding) as handle:
        for line in handle:
            line = line.rstrip("\r\n")
            parts = line.split(spec.separator, limit)

            if len(parts) > limit:                 # 새 레코드의 첫 줄
                if head is not None and (record := finish(head)) is not None:
                    yield record
                head, chunks = parts[:-1], [parts[-1]]
            elif head is not None:                 # 마지막 필드 안의 개행 — 이어지는 줄
                chunks.append(line)
            elif line.strip():
                # 첫 레코드 앞의 구분자가 모자란 줄. 이어 붙일 레코드가 없다.
                _log.warning(
                    f"[delimited] 필드가 모자란 줄 건너뜀: "
                    f"필드={len(parts)}/{len(spec.columns)} 줄={line[:80]!r}"
                )

    if head is not None and (record := finish(head)) is not None:
        yield record


def read_records(path: str, spec: DelimitedSpec) -> list[dict[str, str]]:
    """레코드 목록. `kind: records` 매핑이 그대로 받는 형태다."""
    records = list(iter_records(path, spec))
    _log.info(f"[delimited] 레코드 읽음: {len(records)}건 separator={spec.separator!r}")
    return records
