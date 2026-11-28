"""doc_type 등록 명령 — `python -m genon.preprocessor.activities doc-types list | validate | add | remove | rename`.

parse activity 폴더(`activities/<이름>/`)의 doc_type 등록을 읽고 더하고 뺀다. 등록은 규칙 파일
`custom_field_<doc_type>.yaml` 최상위의 `doc_type:` 한 가지다(#748·#798). 규칙 파일이 있으면 등록이고 지우면 빠진다.
`config.yaml` 은 읽기만 하고 고치지 않으므로 기본 activity `parse` 에도 `add`·`remove` 할 수 있다.
`config.yaml` 에 `- custom_fields:` 등록 블록이 남아 있으면 worker 가 기동하지 못하므로 이 명령도 거부한다.
전처리 Studio 가 코드스페이스의 서빙본 체크아웃에서 부른다 — worker 는 이 모듈을 쓰지 않는다.

판정은 worker 가 쓰는 함수를 그대로 부른다. 이름 비교는 `normalize_doc_type(s)`, 규칙 파일 읽기는
`load_custom_fields_config`, 규칙 파일 검사는 `tools/config_precheck/precheck_custom_fields.py` 의 `check_block`.
규칙 파일 등록 찾기는 worker 와 같은 `config_v2.rule_file_registrations` 다.
이 모듈이 새로 하는 일은 단계별 결과 모으기와 규칙 파일의 텍스트 수정이다.

규칙 파일은 주석이 문서 역할을 하므로(Studio 툴팁) YAML 로 다시 쓰지 않고 필요한 줄만 텍스트로 고친다.
고친 결과는 다시 읽어 의도한 값만 달라졌는지 확인한 뒤에만 쓴다.

실패 사유(`error.detail.reason`)는 이 파일의 `DocTypeError` 호출부가 전부다. 문서 처리 실패의 사유 코드
(`processing/common/reason_codes.py`)와는 별개다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from genon.preprocessor.activities import _folders

PARSE_STAGE = "parse"
BLOCK_KEY = "custom_fields"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")          # add --name 에만 적용한다. pipeline 의 doc_type 이름 규칙과 같다
DOC_TYPE_KEY = "doc_type"
# 규칙 파일 최상위의 `doc_type:` 줄과 `schema:` 줄 — `add` 가 복사본에 doc_type 을 적을 자리를 찾는다.
_DOC_TYPE_LINE_RE = re.compile(r"^doc_type[ ]*:")
_SCHEMA_LINE_RE = re.compile(r"^schema[ ]*:")


class DocTypeError(ValueError):
    """`doc-types` 명령이 거부한 요청. 같은 입력이면 결과가 같으므로 다시 시도하지 않는다."""

    non_retryable = True

    def __init__(self, reason: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.detail: dict[str, Any] = {"reason": reason, **detail}


@dataclass(frozen=True)
class _Activity:
    """activity 하나의 설정 폴더와 읽은 `config.yaml`."""

    name: str
    folder: Path
    config_path: Path
    config: dict
    registrations: list[dict]           # 규칙 파일 등록 `{doc_type, config_file}`(파일 이름 순)
    presets: dict                       # 규칙 파일의 `model_preset:` 을 펼 때 쓴다

    def label(self, name: str = _folders.CONFIG_FILE) -> str:
        return f"activities/{self.name}/{name}"


def rule_file_name(doc_type: str) -> str:
    return f"custom_field_{doc_type}.yaml"


def _load(activity: str, activities_dir: Path | None) -> _Activity:
    from genon.preprocessor.processing.common import config_parse as cp
    from genon.preprocessor.processing.enrichment import config_v2
    from genon.preprocessor.processing.enrichment.enrichment_config import reject_registration_blocks

    root = activities_dir or _folders.ACTIVITIES_DIR
    known = _folders.slugs(root)
    if activity not in known:
        raise DocTypeError("activity_not_found",
                           f"activity 없음: {activity!r} (있는 것: {', '.join(known) or '<없음>'})")
    if _folders.stage_of(activity) != PARSE_STAGE:
        raise DocTypeError("not_parse_activity",
                           f"activity {activity!r} 는 parse 단계가 아님: doc_type 은 parse activity 에만 등록함")
    folder = root / activity
    config_path = folder / _folders.CONFIG_FILE
    where = f"activities/{activity}/{_folders.CONFIG_FILE}"
    if not config_path.is_file():
        raise DocTypeError("config_invalid", f"{where} 없음")
    try:
        config = cp.read_yaml_file(config_path)
    except ValueError as exc:
        raise DocTypeError("config_invalid", f"{where} 읽기 실패: {exc}") from exc
    if not isinstance(config, dict):
        raise DocTypeError("config_invalid", f"{where} 읽기 실패: 최상위가 mapping 이 아님")
    enrichment = config.get("enrichment") or []
    if not isinstance(enrichment, list):
        raise DocTypeError("config_invalid", f"{where} 읽기 실패: enrichment 가 목록이 아님")
    try:
        reject_registration_blocks([item[BLOCK_KEY] for item in enrichment
                                    if isinstance(item, dict) and isinstance(item.get(BLOCK_KEY), dict)])
    except ValueError as exc:                        # worker 가 기동하지 못하는 설정이다
        raise DocTypeError("config_invalid", f"{where}: {exc}") from exc
    presets = cp.collect_model_presets(config, str(config_path), strict=False)
    try:
        registrations = config_v2.rule_file_registrations(folder)
    except ValueError as exc:
        raise DocTypeError("config_invalid", f"activities/{activity} 의 규칙 파일 읽기 실패: {exc}") from exc
    return _Activity(activity, folder, config_path, config, registrations, presets)


def _doc_types_of(block: dict) -> tuple[str, ...]:
    from genon.preprocessor.processing.enrichment.custom_fields_enricher import normalize_doc_types

    return normalize_doc_types(block.get("doc_type"))


def _normalize(name: str) -> str:
    from genon.preprocessor.processing.enrichment.custom_fields_enricher import normalize_doc_type

    return normalize_doc_type(name)


def _config_file_of(block: dict) -> str | None:
    return str(block.get("config_file") or "").strip() or None


def _description(folder: Path, config_file: str | None) -> str | None:
    """규칙 파일 첫 줄의 주석(`#` 뒤 그대로). 주석이 아니거나 파일이 없으면 None."""
    from genon.preprocessor.processing.enrichment.custom_fields_enricher import resolve_custom_fields_config_path

    if not config_file:
        return None
    try:
        with resolve_custom_fields_config_path(config_file, str(folder)).open(encoding="utf-8") as f:
            first = f.readline()
    except (OSError, ValueError):
        return None
    return first.lstrip("#").strip() or None if first.startswith("#") else None


def list_doc_types(activity: str = PARSE_STAGE, activities_dir: Path | None = None) -> dict:
    """모든 등록 → `{activity, unknown_doc_type, doc_types: [{doc_type, config_file, enable, description,
    registered_in, removable, copyable}]}`.

    규칙 파일 이름 순이다. 규칙 파일의 `doc_type` 이 목록이면 이름마다 한 항목이다.
    등록은 규칙 파일 한 가지라 `enable` 은 늘 true, `registered_in` 은 늘 `rule_file` 이다(Studio 응답 형태 유지).
    `removable` 은 `remove --name <doc_type>` 이, `copyable` 은 `add --from <doc_type>` 이 거부하지 않는지다.
    두 값은 그 명령의 거부 검사(`_removal`·`_copy_check`)를 그대로 불러 정하므로 명령 결과와 어긋나지 않는다.
    """
    from genon.preprocessor.processing.common.parser_config import resolve_unknown_doc_type_policy

    act = _load(activity, activities_dir)
    defaults = act.config.get("defaults")
    try:
        policy = resolve_unknown_doc_type_policy((defaults if isinstance(defaults, dict) else {}).get("unknown_doc_type"))
    except ValueError as exc:
        raise DocTypeError("config_invalid", f"{act.label()} 읽기 실패: {exc}") from exc
    entries = []
    for block in act.registrations:
        config_file = _config_file_of(block)
        for doc_type in _doc_types_of(block):
            entries.append({"doc_type": doc_type, "config_file": config_file, "enable": True,
                            "description": _description(act.folder, config_file),
                            "registered_in": "rule_file",
                            "removable": _passes(_removal, act, doc_type),
                            "copyable": _passes(_copy_check, act, doc_type)})
    return {"activity": act.name, "unknown_doc_type": policy, "doc_types": entries}


def _passes(check, act: _Activity, doc_type: str) -> bool:
    """거부 검사 `check(act, doc_type)` 가 `DocTypeError` 없이 끝나는지."""
    try:
        check(act, doc_type)
    except DocTypeError:
        return False
    return True


def _step(step: str, status: str, reason: str | None = None, message: str | None = None) -> dict:
    return {"step": step, "status": status, **({"reason": reason, "message": message} if reason else {})}


def _check_rule_file(act: _Activity, block: dict, doc_type: str) -> dict:
    """규칙 파일 등록이 가리키는 규칙 파일이 있고, worker 기동 때와 같은 검사를 통과하는지."""
    from genon.preprocessor.processing.enrichment.custom_fields_enricher import load_custom_fields_config
    from genon.preprocessor.tools.config_precheck import precheck_custom_fields as precheck

    config_file = _config_file_of(block)
    if config_file:
        try:
            load_custom_fields_config(config_file, str(act.folder))
        except FileNotFoundError:
            return _step("config_file", "fail", "config_file_missing",
                         f"doc_type={doc_type} 규칙 파일 없음: {act.label(config_file)}")
        except ValueError as exc:
            return _step("config_file", "fail", "config_invalid", f"doc_type={doc_type} 규칙 파일 오류: {exc}")
    try:
        problems = precheck.check_block(_folders.CONFIG_FILE, block, act.folder, set(), act.presets)
    except SystemExit as exc:                        # precheck 의 load_yaml 은 읽지 못한 파일을 SystemExit 로 알린다
        problems = [f"[기동실패] {exc}"]
    blocking = [p.removeprefix("[기동실패]").strip() for p in problems if p.startswith("[기동실패]")]
    if blocking:
        more = f" (외 {len(blocking) - 1}건)" if len(blocking) > 1 else ""
        return _step("config_file", "fail", "config_invalid",
                     f"doc_type={doc_type} 규칙 파일 오류{more}: {blocking[0]}")
    return _step("config_file", "pass")


def _validate(act: _Activity, doc_type: str) -> list[dict]:
    matches = [b for b in act.registrations if doc_type in _doc_types_of(b)]
    rest = [_step("block", "skip"), _step("config_file", "skip")]
    if not matches:
        return [_step("registered", "fail", "not_registered",
                      f"doc_type={doc_type} 등록 없음: activities/{act.name} 에 doc_type 을 적은 규칙 파일 없음"),
                *rest]
    # `block` 단계는 등록 블록 검사 자리였다. 규칙 파일 등록에는 꺼짐·파일 이름 불일치가 없어 늘 통과다(응답 형태 유지).
    # 규칙 파일 여러 개가 같은 doc_type 을 등록하면 모두 적용되므로 파일마다 검사하고 첫 실패를 보인다.
    checks = [_check_rule_file(act, block, doc_type) for block in matches]
    return [_step("registered", "pass"), _step("block", "pass"),
            next((c for c in checks if c["status"] == "fail"), checks[0])]


def _is_valid(steps: list[dict]) -> bool:
    return all(step["status"] != "fail" for step in steps)


def validate_doc_type(name: str, activity: str = PARSE_STAGE, activities_dir: Path | None = None) -> dict:
    """등록 상태 검사 → `{valid, doc_type, steps}`. 검사 결과가 실패여도 예외가 아니다(`valid: false`)."""
    act = _load(activity, activities_dir)
    doc_type = _normalize(name)
    steps = _validate(act, doc_type)
    return {"valid": _is_valid(steps), "doc_type": doc_type, "steps": steps}


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")          # 줄바꿈(CRLF 포함)을 그대로 둔다


def _with_doc_type(text: str, doc_type: str | list[str], label: str) -> str:
    """규칙 파일 본문의 최상위 `doc_type:` 을 `doc_type` 으로 맞춘 본문. 그 밖의 줄은 한 글자도 바꾸지 않는다.

    `doc_type:` 줄이 있으면 그 줄을 바꾸고, 없으면 `schema:` 줄 바로 아래에 넣는다. 목록은 `[a, b]` 한 줄로 적는다.
    """
    lines = text.splitlines(keepends=True)
    cannot = DocTypeError("config_invalid",
                          f"{label} 에 doc_type 기록 실패: 최상위 `schema:` 줄이나 한 줄짜리 `doc_type:` 줄을 찾지 못함\n"
                          "규칙 파일 최상위에 `schema: v2` 를 한 줄로 적은 형식으로 수정 필요")
    try:
        before = yaml.safe_load(text)
    except yaml.YAMLError:
        raise cannot from None
    at = next((i for i, line in enumerate(lines) if _DOC_TYPE_LINE_RE.match(line)), None)
    schema = next((i for i, line in enumerate(lines) if _SCHEMA_LINE_RE.match(line)), None)
    if not isinstance(before, dict) or (at is None and schema is None):
        raise cannot
    anchor = lines[at if at is not None else schema]
    newline = "\r\n" if anchor.endswith("\r\n") else "\n"
    if not anchor.endswith(("\n", "\r")):
        lines[lines.index(anchor)] = anchor + newline
    value = f"[{', '.join(doc_type)}]" if isinstance(doc_type, list) else doc_type
    written = f"doc_type: {value}{newline}"
    if at is not None:
        lines[at] = written
    else:
        lines.insert(schema + 1, written)
    new_text = "".join(lines)
    # 고친 결과를 다시 읽어 확인한다 — doc_type 값 하나만 달라야 한다.
    try:
        after = yaml.safe_load(new_text)
    except yaml.YAMLError:
        raise cannot from None
    if after != {**before, DOC_TYPE_KEY: doc_type}:
        raise cannot
    return new_text


def _titled(text: str, doc_type: str, title: str | None) -> str:
    """규칙 파일 본문의 첫 줄 주석을 `--title` 로 바꾼다. 첫 줄이 주석이 아니면 그 위에 넣는다."""
    if not title:
        return text
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    lines[0:1 if lines and lines[0].startswith("#") else 0] = [
        f"# 문서 유형 {doc_type}({title})의 custom_fields 설정{newline}"]
    return "".join(lines)


def _copy_source(act: _Activity, origin: str) -> Path:
    """`add --from <origin>` 이 복사할 규칙 파일. 복사할 수 없으면 `DocTypeError`."""
    from genon.preprocessor.processing.enrichment.custom_fields_enricher import resolve_custom_fields_config_path

    sources = [b for b in act.registrations if _normalize(origin) in _doc_types_of(b)]
    if not sources:
        known = sorted({d for b in act.registrations for d in _doc_types_of(b)})
        raise DocTypeError("source_not_found",
                           f"--from doc_type={origin} 등록 없음: activities/{act.name} "
                           f"(등록된 것: {', '.join(known) or '<없음>'})")
    if len(sources) > 1:
        # 규칙 파일 하나만 복사하면 복사본은 원본 doc_type 의 일부만 처리한다
        raise DocTypeError("multiple_rule_files",
                           f"--from doc_type={origin} 복사 불가: 규칙 파일 {len(sources)}개가 등록함 "
                           f"({', '.join(_config_file_of(b) or '?' for b in sources)})\n"
                           "규칙 파일을 직접 복사해 각 파일 맨 위의 doc_type 수정 필요")
    source_file = _config_file_of(sources[0])
    try:
        source_path = resolve_custom_fields_config_path(source_file, str(act.folder)) if source_file else None
    except ValueError:
        source_path = None
    if source_path is None or not source_path.is_file():
        raise DocTypeError("config_file_missing",
                           f"--from doc_type={origin} 의 규칙 파일 없음: {act.label(source_file or '<config_file 없음>')}")
    return source_path


def _copy_check(act: _Activity, origin: str) -> None:
    """`list` 의 `copyable` — `add --from <origin>` 이 하는 거부 검사 전부(원본 찾기, 복사본에 doc_type 줄 적기)."""
    source_path = _copy_source(act, origin)
    _with_doc_type(_read_text(source_path), "copy_check", act.label(source_path.name))


def add_doc_type(name: str, origin: str, activity: str, title: str | None = None,
                 activities_dir: Path | None = None, from_activity: str | None = None) -> tuple[dict, list[Path]]:
    """parse activity 에 doc_type 을 등록한다 → (`{doc_type, activity}`, 만든 파일 [규칙 파일]).

    `origin` doc_type 의 규칙 파일을 `custom_field_<name>.yaml` 로 복사하고 그 파일 최상위에 `doc_type: <name>` 을
    적는다. 이 한 줄이 등록이다 — `config.yaml` 은 고치지 않으므로 기본 activity `parse` 에도 쓸 수 있다.
    `origin` 은 `from_activity`(없으면 `activity`)에 등록된 doc_type 이다. `from_activity` 가 다른 activity 면 그 폴더의
    규칙 파일을 읽어 `activity` 폴더에 쓴다 — `name` 이 `origin` 과 같아도 된다.
    거부할 때는 `DocTypeError` 를 올리고 어떤 파일도 만들지 않는다.
    """
    act = _load(activity, activities_dir)
    source_act = act if from_activity in (None, activity) else _load(from_activity, activities_dir)
    if not NAME_RE.fullmatch(name):
        raise DocTypeError("invalid_name", f"doc_type 이름 형식 오류: {name!r} (소문자로 시작, 소문자·숫자·_ 만 허용)")
    registered = [b for b in act.registrations if name in _doc_types_of(b)]
    if registered:
        steps = _validate(act, name)
        problem = next((s["message"] for s in steps if s["status"] == "fail"), None)
        state = "등록 상태 정상" if problem is None else "등록 상태 확인 필요"
        raise DocTypeError(
            "already_registered",
            f"doc_type={name} 이미 등록됨: config_file={_config_file_of(registered[0]) or '<없음>'}, {state}"
            + (f"\n{problem}" if problem else ""),
            steps=steps)
    source_path = _copy_source(source_act, origin)
    target = act.folder / rule_file_name(name)
    if target.exists():
        raise DocTypeError("config_file_exists",
                           f"doc_type={name} 등록 중단: 규칙 파일이 이미 있음 ({act.label(target.name)})\n"
                           "그 파일을 지우거나 다른 이름 지정 필요")
    rule_text = _with_doc_type(_titled(_read_text(source_path), name, title), name, source_act.label(source_path.name))
    with target.open("xb") as f:
        f.write(rule_text.encode("utf-8"))
    return {"doc_type": name, "activity": act.name}, [target]


@dataclass(frozen=True)
class _Removal:
    """`remove` 가 지울 규칙 파일들 — 그 doc_type 을 등록한 파일 전부."""

    doc_type: str
    paths: list[Path]


def _removal(act: _Activity, name: str) -> _Removal:
    """`remove --name <name>` 의 거부 검사 — 파일을 바꾸지 않는다. `list` 의 `removable` 도 이것으로 정한다."""
    want = _normalize(name)
    hits = [b for b in act.registrations if want in _doc_types_of(b)]
    if not hits:
        known = sorted({d for b in act.registrations for d in _doc_types_of(b)})
        raise DocTypeError("not_registered",
                           f"doc_type={name} 삭제 불가: activities/{act.name} 에 등록 없음 "
                           f"(등록된 것: {', '.join(known) or '<없음>'})")
    shared = next((b for b in hits if len(_doc_types_of(b)) > 1), None)
    if shared is not None:
        raise DocTypeError("shared_block",
                           f"doc_type={name} 삭제 불가: 규칙 파일 하나에 여러 doc_type 이 있음 "
                           f"({', '.join(_doc_types_of(shared))})\n"
                           f"{_config_file_of(shared)} 에서 doc_type 목록 직접 수정 필요")
    return _Removal(want, [act.folder / str(_config_file_of(b)) for b in hits])


def remove_doc_type(name: str, activity: str, activities_dir: Path | None = None) -> tuple[dict, list[Path]]:
    """parse activity 에서 doc_type 등록을 뺀다 → (`{doc_type, activity}`, 지운 규칙 파일들).

    `add` 의 반대다. 그 doc_type 을 등록한 규칙 파일을 모두 지운다(`config.yaml` 은 그대로다).
    적재된 문서가 있는지는 확인하지 않는다(pipeline `doc-type-mappings remove` 몫).
    거부할 때는 `DocTypeError` 를 올리고 어떤 파일도 바꾸지 않는다.
    """
    act = _load(activity, activities_dir)
    plan = _removal(act, name)
    for path in plan.paths:
        path.unlink()
    return {"doc_type": plan.doc_type, "activity": act.name}, list(plan.paths)


def rename_doc_type(name: str, to: str, activity: str,
                    activities_dir: Path | None = None) -> tuple[dict, list[Path]]:
    """parse activity 의 doc_type 이름을 그 자리에서 바꾼다 → (`{doc_type, renamed_to, activity}`, 바뀐 파일들).

    그 doc_type 을 등록한 규칙 파일마다 최상위 `doc_type:` 값만 바꾼다(목록이면 그 원소만). 파일 이름이
    `custom_field_<name>.yaml` 인 단일 등록 파일은 `custom_field_<to>.yaml` 로 옮긴다. 바뀐 파일 목록에는 옮기기 전
    경로와 옮긴 뒤 경로가 함께 들어간다(콘솔이 한 커밋에 담는다). pipeline 매핑은 고치지 않는다.
    거부할 때는 `DocTypeError` 를 올리고 어떤 파일도 바꾸지 않는다 — 모든 파일의 새 본문을 먼저 만든 뒤에 쓴다.
    """
    act = _load(activity, activities_dir)
    old = _normalize(name)
    hits = [b for b in act.registrations if old in _doc_types_of(b)]
    if not hits:
        known = sorted({d for b in act.registrations for d in _doc_types_of(b)})
        raise DocTypeError("not_registered",
                           f"doc_type={name} 이름 변경 불가: activities/{act.name} 에 등록 없음 "
                           f"(등록된 것: {', '.join(known) or '<없음>'})")
    if not NAME_RE.fullmatch(to):
        raise DocTypeError("invalid_name", f"doc_type 이름 형식 오류: {to!r} (소문자로 시작, 소문자·숫자·_ 만 허용)")
    taken = next((b for b in act.registrations if to in _doc_types_of(b)), None)
    if taken is not None:
        raise DocTypeError("already_registered",
                           f"doc_type={to} 이미 등록됨: config_file={_config_file_of(taken) or '<없음>'}")
    writes: list[tuple[Path, Path, str]] = []                 # (읽은 경로, 쓸 경로, 새 본문)
    for block in hits:
        source = act.folder / str(_config_file_of(block))
        raw = block.get(DOC_TYPE_KEY)
        value = [to if _normalize(d) == old else d for d in raw] if isinstance(raw, list) else to
        target = source
        if not isinstance(raw, list) and source.name == rule_file_name(old):
            target = act.folder / rule_file_name(to)
            if target.exists():
                raise DocTypeError("config_file_exists",
                                   f"doc_type={name} 이름 변경 중단: 규칙 파일이 이미 있음 ({act.label(target.name)})\n"
                                   "그 파일을 지우거나 다른 이름 지정 필요")
        writes.append((source, target, _with_doc_type(_read_text(source), value, act.label(source.name))))
    files: list[Path] = []
    for source, target, text in writes:
        if target == source:
            source.write_bytes(text.encode("utf-8"))
            files.append(source)
        else:
            with target.open("xb") as f:
                f.write(text.encode("utf-8"))
            source.unlink()
            files += [source, target]
    return {"doc_type": old, "renamed_to": to, "activity": act.name}, files
