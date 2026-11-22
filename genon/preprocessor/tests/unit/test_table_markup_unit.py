"""표 HTML 구조 손상 검사(processing/common/table_markup.py) 단위 테스트(#773).

검사 지점 배선(HTML·마크다운 입력, JSON 본문 병합)은 단건 실행과 parse_chunk_verify 로 확인하고,
레코드 필드 경로는 test_json_records_unit.py 가 본다.
"""
import pytest

from genon.preprocessor.processing.common.table_markup import find_errors

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("html,expected", [
    # docling 에서 셀이 합쳐지거나 행·문단이 빠지는 네 가지
    ("<table><tr><td>a<td>b</td></tr></table>", {"cell_unclosed": 1}),
    ("<table><tr><td>a</td><tr><td>b</td></tr></table>", {"row_unclosed": 1}),
    ("<table><td>a</td></table>", {"cell_outside_row": 1}),
    ("<table><tr><td>a</td></tr><p>다음 문단</p>", {"table_unclosed": 1}),
    # 결과를 해치지 않는 생략·정상 문서에 흔한 형태는 보지 않는다
    ("<table><tr><td>a</td><td>b</tr></table>", {}),
    ("<table><tr><td>a</td></table></table>", {}),
    ("<table><tr><td><table><tr><td>안</td></tr></table></td></tr></table>", {}),
    ("<p>표 없음 <td 같은 글자</p>", {}),
])
def test_find_errors(html, expected):
    assert dict(find_errors(html)[0]) == expected


@pytest.mark.parametrize("text,expected", [
    ("예시\n```html\n<table><tr><td>예시\n```\n`<td>` 태그", {}),
    ("예시\n\n    <table><tr><td>예시\n", {}),                    # 들여쓰기 코드 블록
    ("> ```html\n> <table><tr><td>예시\n> ```\n", {}),          # 인용 안 코드 블록
    # 닫는 줄로 보이지만 닫는 줄이 아닌 경우: 뒤의 실제 표는 그대로 본다
    ("```html\n코드\n```not-a-close\n코드\n```\n\n<table><td>실제 표</td></table>\n",
     {"cell_outside_row": 1}),
    ("본문\n\n<table><tr><td>a</td></tr>\n", {"table_unclosed": 1}),
])
def test_find_errors_reads_markdown_html_blocks_only(text, expected):
    """#777: 마크다운은 docling 처럼 marko 로 읽어 HTML 블록만 본다. 코드 안의 태그는 표가 아니다."""
    assert dict(find_errors(text, markdown=True)[0]) == expected
