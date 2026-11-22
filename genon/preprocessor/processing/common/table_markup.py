"""표 HTML 구조 손상 검사(#773).

docling 의 HTML 백엔드는 html.parser 로 읽어 HTML 표준의 닫는 태그 생략 규칙을 적용하지
않는다. 아래 네 가지는 표준상 허용되는 생략이라도 셀이 합쳐지거나 행·문단이 빠진 채 오류 없이
파싱되므로, docling 에 넘기기 직전의 HTML 에서 찾아 처리를 멈춘다(PARSE_D015).

  셀이 닫히지 않은 채 다음 셀이 시작됨       <td>a<td>b
  행이 닫히지 않은 채 다음 행이 시작됨       <tr><td>a</td><tr>
  <tr> 밖에 있는 셀                         <table><td>a</td></table>
  끝까지 닫히지 않은 <table>

</tr>·</table> 바로 앞의 생략, 여분의 </table>, 표 안의 표는 결과를 해치지 않거나 정상 문서에
흔해 보지 않는다. 검사 여부는 요청 단위 ContextVar 로 켠다 — 레코드 필드 변환(html_to_text)은
호출부가 여럿이라 인자로 넘기지 않는다.
"""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from html.parser import HTMLParser

from genon.preprocessor.processing.common.reason_codes import CodedValueError

REASON_CODE = "PARSE_D015"
_ENABLED: ContextVar[bool] = ContextVar("verify_table_markup", default=False)
_CELLS = frozenset({"td", "th"})
_LABELS = {
    "cell_unclosed": "셀 닫는 태그 누락",
    "row_unclosed": "행 닫는 태그 누락",
    "cell_outside_row": "<tr> 밖의 셀",
    "table_unclosed": "</table> 누락",
}


class _TableCheck(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list = []          # 열린 표마다 [행 열림, 셀 열림, 시작 줄]
        self.errors: Counter = Counter()
        self.first: dict = {}

    def _hit(self, kind: str, line: int = 0) -> None:
        self.errors[kind] += 1
        self.first.setdefault(kind, line or self.getpos()[0])

    def handle_starttag(self, tag, attrs):
        top = self.tables[-1] if self.tables else None
        if tag == "table":
            self.tables.append([False, False, self.getpos()[0]])
        elif top is None:
            return
        elif tag == "tr":
            if top[0]:
                self._hit("row_unclosed")
            top[0], top[1] = True, False
        elif tag in _CELLS:
            if not top[0]:
                self._hit("cell_outside_row")
            elif top[1]:
                self._hit("cell_unclosed")
            top[1] = True

    def handle_endtag(self, tag):
        if not self.tables:
            return
        top = self.tables[-1]
        if tag in _CELLS:
            top[1] = False
        elif tag == "tr":
            top[0] = top[1] = False
        elif tag == "table":
            self.tables.pop()


def find_errors(html: str, markdown: bool = False) -> tuple:
    """(종류별 건수, 종류별 첫 줄 번호). 손상이 없으면 빈 Counter.

    markdown 이면 docling 마크다운 백엔드처럼 marko 로 읽어 HTML 블록만 이어 붙여 본다. 코드 블록·
    인라인 코드 안의 태그는 HTML 로 넘어가지 않으므로 보지 않는다. 이때 줄 번호는 이어 붙인 HTML
    기준이다.
    """
    if "<t" not in html.lower():
        return Counter(), {}
    if markdown:
        html = _markdown_html_blocks(html)
    checker = _TableCheck()
    checker.feed(html)
    checker.close()
    for table in checker.tables:
        checker._hit("table_unclosed", table[2])
    return checker.errors, checker.first


def _markdown_html_blocks(text: str) -> str:
    import marko
    import marko.block

    blocks: list = []

    def walk(element) -> None:
        if isinstance(element, marko.block.HTMLBlock):
            blocks.append(element.body)
            return
        for child in getattr(element, "children", None) or ():
            if not isinstance(child, str):
                walk(child)

    walk(marko.Markdown().parse(text))
    return "\n".join(blocks)


def enable(flag: bool):
    """요청 범위에서 검사를 켜고 끈다. 돌려준 token 은 요청이 끝날 때 reset 에 넘긴다."""
    return _ENABLED.set(bool(flag))


def is_enabled() -> bool:
    return _ENABLED.get()


def reset(token) -> None:
    _ENABLED.reset(token)


def check(html: str, where: str, markdown: bool = False) -> None:
    """검사가 켜져 있고 손상이 있으면 PARSE_D015 로 멈춘다. where 는 오류 첫 줄의 대상 이름이다."""
    if not _ENABLED.get() or not isinstance(html, str):
        return
    errors, first = find_errors(html, markdown)
    if not errors:
        return
    # 마크다운은 HTML 블록만 이어 붙여 보므로 줄 번호가 원문과 맞지 않아 싣지 않는다.
    detail = ", ".join(f"{_LABELS[k]} {n}건" + ("" if markdown else f"(첫 위치 {first[k]}줄)")
                       for k, n in errors.items())
    raise CodedValueError(f"{where} 처리 불가: 표 HTML 구조 손상({detail})\n원천 HTML 의 표 태그 수정 필요",
                          REASON_CODE)
