"""원본·파싱 페이지 대조(processing/common/page_check.py) 단위 테스트(#771).

파서 배선은 단건 실행(activities run)과 parse_chunk_verify 로 확인한다. 여기서는 원본 파일을
실제로 만들어 셈과 미추출 판정만 본다.
"""
import openpyxl
import pypdfium2
import pytest
from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem, Size
from docling_core.types.doc.document import ContentLayer
from pptx import Presentation

from genon.preprocessor.processing.common import page_check as pc

pytestmark = pytest.mark.unit


def _prov(page: int) -> ProvenanceItem:
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, 1))


def _pdf(path, pages: int) -> None:
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(100, 100)
    pdf.save(str(path))


def _pptx(path, slides: int, hidden: int) -> None:
    prs = Presentation()
    for i in range(slides):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        if i < hidden:
            slide._element.set("show", "0")
    prs.save(str(path))


def _document() -> DoclingDocument:
    """1쪽: 그림 안의 글자, 2쪽: 그림만, 3쪽: 꼬리말만, 4쪽: 파서가 덧붙인 페이지 설명만."""
    doc = DoclingDocument(name="d")
    for page in range(1, 5):
        doc.add_page(page_no=page, size=Size(width=1, height=1))
    picture = doc.add_picture(prov=_prov(1))
    doc.add_text(label=DocItemLabel.TEXT, text="슬라이드 본문", prov=_prov(1), parent=picture)
    doc.add_picture(prov=_prov(2))
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="- 3 -", prov=_prov(3),
                 content_layer=ContentLayer.FURNITURE)
    doc.add_text(label=DocItemLabel.TEXT, text="[설명]\n그림 설명", prov=_prov(4))
    return doc


@pytest.mark.parametrize("ext,make,source,hidden", [
    (".pdf", lambda p: _pdf(p, 5), 5, 0),               # 파싱에서 한 쪽이 빠짐
    (".pptx", lambda p: _pptx(p, 5, 1), 5, 1),          # 숨김 슬라이드는 PDF 변환에서 빠짐
])
def test_check_document_counts_source_and_empty_pages(tmp_path, ext, make, source, hidden):
    path = tmp_path / f"doc{ext}"
    make(path)

    check = pc.check_document(str(path), ext, _document(), ignore_prefixes=("[설명]",))

    assert check == {"unit": "page" if ext == ".pdf" else "slide", "source": source, "hidden": hidden,
                     "parsed": 4, "empty_count": 2, "empty_pages": [3, 4], "image_only_pages": [2]}


def test_check_sheets_counts_sheets_without_rows(tmp_path):
    path = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "데이터"
    wb.create_sheet("빈 시트")
    wb.create_sheet("숨김").sheet_state = "hidden"
    wb.save(path)
    data = {"data": [{"sheet_name": "데이터", "data_rows": [{"a": 1}]},
                     {"sheet_name": "숨김", "data_rows": [{"a": 2}]}],
            "sheet_names": ["데이터", "빈 시트", "숨김"]}

    assert pc.check_sheets(str(path), ".xlsx", data) == {
        "unit": "sheet", "source": 3, "hidden": 1, "parsed": 2, "empty_count": 1,
        "empty_pages": ["빈 시트"], "image_only_pages": []}
    # 설정이 시트를 골랐으면 고르지 않은 시트는 미추출로 세지 않는다.
    assert pc.check_sheets(str(path), ".xlsx", data, only_sheets={"데이터"})["empty_pages"] == []
