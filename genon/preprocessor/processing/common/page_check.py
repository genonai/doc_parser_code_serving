"""원본과 파싱 결과의 페이지 수 대조, 내용 미추출 페이지 집계(#771).

파싱 응답 `usage.page_check` 에 싣는 값을 만든다. 처리를 막지 않는 보고 항목이다.
대상은 pdf(페이지)·pptx(슬라이드)·xlsx/xlsm(시트)이고 그 밖의 형식은 None 을 돌려 싣지 않는다.
docling 타입은 import 하지 않고 duck typing 으로 읽는다.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional

_log = logging.getLogger(__name__)

_UNITS = {".pdf": "page", ".pptx": "slide", ".xlsx": "sheet", ".xlsm": "sheet"}
_PICTURE_LABELS = frozenset({"picture", "chart"})


def _source_pages(path: str, ext: str) -> Optional[tuple]:
    """(원본 수, 숨김 수). 읽지 못하면 None — 보고 항목이라 파싱을 막지 않는다."""
    try:
        if ext == ".pdf":
            import pypdfium2

            pdf = pypdfium2.PdfDocument(path)
            try:
                return len(pdf), 0
            finally:
                pdf.close()
        if ext == ".pptx":
            from pptx import Presentation

            slides = list(Presentation(path).slides)
            # 숨김 슬라이드는 PDF 로 바꿀 때 빠진다.
            return len(slides), sum(1 for s in slides if s._element.get("show") in ("0", "false"))
        if ext in (".xlsx", ".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(path, read_only=True)
            try:
                return len(wb.sheetnames), sum(1 for ws in wb.worksheets if ws.sheet_state != "visible")
            finally:
                wb.close()
    except Exception as exc:
        _log.info(f"{os.path.basename(path)}: 원본 페이지 수 확인 건너뜀 ({type(exc).__name__}: {exc})")
    return None


def _has_text(item: Any) -> bool:
    data = getattr(item, "data", None)
    cells = getattr(data, "table_cells", None)
    if cells is not None:
        return any(str(getattr(cell, "text", "") or "").strip() for cell in cells)
    return bool(str(getattr(item, "text", "") or "").strip())


def check_document(path: str, ext: str, doc: Any, ignore_prefixes: Iterable[str] = ()) -> Optional[dict]:
    """docling 문서의 페이지 대조 결과. 대상 형식이 아니거나 원본을 못 읽으면 None.

    본문(BODY) 아이템만 본다 — 머리말·꼬리말만 남은 페이지는 미추출이다. 글자·표가 없고
    그림만 있으면 image_only_pages 로 따로 센다. ignore_prefixes 로 시작하는 텍스트(파서가
    덧붙인 페이지 설명 등)는 추출된 내용으로 세지 않는다.
    """
    unit = _UNITS.get(ext)
    if unit is None:
        return None
    source = _source_pages(path, ext)
    if source is None:
        return None
    prefixes = tuple(ignore_prefixes)
    text_pages: set = set()
    image_pages: set = set()
    # PDF 로 바꾼 슬라이드는 글자가 그림 영역 안에 들어가는 경우가 있어 그림 안쪽까지 본다.
    for item, _ in doc.iterate_items(traverse_pictures=True):
        for prov in getattr(item, "prov", None) or ():
            page = getattr(prov, "page_no", None)
            label = str(getattr(getattr(item, "label", ""), "value", getattr(item, "label", "")))
            if label in _PICTURE_LABELS:
                image_pages.add(page)
            elif _has_text(item) and not str(getattr(item, "text", "") or "").startswith(prefixes):
                text_pages.add(page)
    pages = sorted(getattr(doc, "pages", None) or {})
    empty = [p for p in pages if p not in text_pages]
    return _summary(unit, source, len(pages),
                    [p for p in empty if p not in image_pages],
                    [p for p in empty if p in image_pages])


def check_sheets(path: str, ext: str, data_dict: dict, only_sheets: Optional[set] = None) -> Optional[dict]:
    """tabular 경로의 시트 대조 결과. 데이터 행이 하나도 없는 시트를 미추출로 센다.

    only_sheets 가 있으면(설정이 시트를 골랐으면) 그 밖의 시트는 미추출로 세지 않는다.
    """
    unit = _UNITS.get(ext)
    if unit != "sheet":
        return None
    source = _source_pages(path, ext)
    if source is None:
        return None
    with_rows = {t.get("sheet_name") for t in data_dict.get("data") or () if t.get("data_rows")}
    names = [n for n in data_dict.get("sheet_names") or () if only_sheets is None or n in only_sheets]
    return _summary(unit, source, len(with_rows), [n for n in names if n not in with_rows], [])


def _summary(unit: str, source: tuple, parsed: int, empty: list, image_only: list) -> dict:
    count, hidden = source
    return {"unit": unit, "source": count, "hidden": hidden, "parsed": parsed,
            "empty_count": len(empty), "empty_pages": empty, "image_only_pages": image_only}


def attach(result: dict, check: Optional[dict], file_name: str, request: Any = None) -> dict:
    """응답 usage 와 요청 상태에 대조 결과를 싣고, 미추출이 있거나 수가 맞지 않으면 warning 을 남긴다.

    워커는 docling 형식 응답에서 document 만 저장하므로 usage 가 남지 않는다. 그래서
    chunk_validation 처럼 요청 상태(request.state.page_check)에도 올려 activity 결과에 싣게 한다.
    """
    if not check or not isinstance(result, dict):
        return result
    state = getattr(request, "state", None)
    if state is not None:
        state.page_check = check
    usage = result.get("usage")
    if not isinstance(usage, dict):
        usage = result["usage"] = {}
    usage["page_check"] = check
    unit = {"page": "페이지", "slide": "슬라이드", "sheet": "시트"}[check["unit"]]
    if check["empty_count"]:
        _log.warning(f"{file_name} 내용 미추출 {unit} {check['empty_count']}/{check['parsed']}: "
                     f"{', '.join(map(str, check['empty_pages'][:20]))}")
    if check["unit"] != "sheet" and check["source"] - check["hidden"] != check["parsed"]:
        _log.warning(f"{file_name} {unit} 수 불일치: 원본 {check['source']}(숨김 {check['hidden']}), "
                     f"파싱 {check['parsed']}")
    return result
