"""글자 수 청킹(chunk_mode=character) 분할 계약.

분할 계산(char_split.split_spans)과, 그 결과로 청커가 만든 chunk 의 표 조각 기록을 본다.
"""

import math

import pytest

from genon.preprocessor.processing.chunking import char_split as cs


@pytest.mark.unit
@pytest.mark.parametrize("texts, size, overlap, first_end", [
    (["가나다 라마바", "사아자"], 5, 0, 4),            # 앞당길 범위가 1글자 미만이면 1글자 안에서 찾음
    (["가" * 250], 100, 30, 100),                    # overlap
    (["abc", "", "def"], 100, 0, 7),                 # 빈 그림 항목(길이 0 구간)
    (["x" * 95, "y" * 20], 100, 0, 96),              # 줄바꿈에서 자름
    (["a" * 93 + " " + "b" * 20], 100, 0, 94),       # 줄바꿈이 없으면 공백에서 자름
    (["a" * 25], 10, 0, 10),                         # 자를 곳이 없으면 정확한 글자 수
])
def test_split_spans(texts, size, overlap, first_end):
    spans = cs.split_spans(texts, size, overlap, "\n")
    full = "\n".join(t for t in texts if t)

    assert spans[0].own_e == first_end
    assert "".join(full[sp.own_s:sp.own_e] for sp in spans) == full
    assert all(len(sp.text) <= size for sp in spans)
    assert all(sp.items for sp in spans)
    assert set().union(*(sp.items for sp in spans)) == set(range(len(texts)))


def _table_doc(rows):
    core = pytest.importorskip("docling_core.types.doc", exc_type=ImportError)
    doc = core.DoclingDocument(
        name="char_table",
        origin=core.DocumentOrigin(mimetype="text/html", binary_hash=1, filename="char_table.html"),
    )
    doc.add_heading(text="표 절")
    doc.add_text(label=core.DocItemLabel.TEXT, text="앞 문단")
    values = [["항목", "값"]] + [[f"항목-{i}", str(i * 1000)] for i in range(rows)]
    cells = [
        core.TableCell(text=value, start_row_offset_idx=r, end_row_offset_idx=r + 1,
                       start_col_offset_idx=c, end_col_offset_idx=c + 1, column_header=(r == 0))
        for r, row in enumerate(values) for c, value in enumerate(row)
    ]
    doc.add_table(data=core.TableData(num_rows=len(values), num_cols=2, table_cells=cells))
    return doc


@pytest.mark.unit
def test_character_table_over_two_chunks():
    """표가 두 chunk 에 걸치면 두 chunk 모두 표를 담고 표 조각 수 2 가 기록되며 HEADER 경로가 없다."""
    module = pytest.importorskip("genon.preprocessor.facade.chunking_processor", exc_type=ImportError)

    def run(size):
        chunker = module.GenosSmartChunker(
            max_tokens=size, chunk_mode="character", tokenizer_type="char")
        return chunker, list(chunker.chunk(dl_doc=_table_doc(40), export_to_html=1))

    _, whole = run(0)
    chunker, chunks = run(math.ceil(len(whole[0].text) * 0.6))

    ref = _table_doc(40).tables[0].self_ref
    assert len(chunks) == 2
    assert all(ref in [it.self_ref for it in c.meta.doc_items] for c in chunks)
    assert chunker._table_split_totals == {ref: 2}
    # headings 가 없으면 compose_vectors 가 `HEADER:` 줄을 붙이지 않는다(header_path.build_header_line).
    assert all(c.meta.headings is None for c in chunks)
