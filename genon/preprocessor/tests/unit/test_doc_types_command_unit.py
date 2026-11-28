"""`activities doc-types list | validate | add | remove | rename` (#712, #739, #748, #798, #808)와 `new --doc-type`(#822) — 임시 activities 폴더에서 doc_type 등록을 다룬다.

전처리 Studio 가 코드스페이스에서 부르는 명령이다. 등록은 규칙 파일 최상위의 `doc_type:` 한 가지다. 거부할 때 어떤
파일도 바뀌지 않는지, `add`·`remove` 가 규칙 파일만 만들고 지우며 `config.yaml` 을 고치지 않는지, 결과 줄(`@@RESULT@@`)의
`error.detail.reason` 이 계약대로인지를 본다.
"""
import importlib
import json
from pathlib import Path

import pytest
import yaml

from genon.preprocessor.activities import _doc_types, _folders
from genon.preprocessor.activities._doc_types import DocTypeError

pytestmark = pytest.mark.unit

# 기본 activity parse 의 설정을 줄인 것. doc_type 등록은 규칙 파일에 있으므로 custom_fields 항목이 없다.
CONFIG = """\
# Studio 는 옵션 이름 옆 툴팁에 그 키의 주석을 보여 준다.
defaults:
  log_level: 4
  # warn(기본)=경고만 | fail=요청을 실패시킨다
  unknown_doc_type: fail

enrichment:
  # 목차 추출
  - toc:
      enable: false

output:
  format: "docling"
"""

# genon/sites/monimo/activities/parse/custom_field_music_ai.yaml 을 줄인 것(LLM 을 쓰지 않는 레코드 매핑).
RULE = """\
# 모니모 뮤직 AI 플레이리스트 문구 JSON 레코드
#
# playList 항목 하나가 chunk 하나다.

schema: v2
source:
  kind: records
  records_at: playList
  on_missing: error
fields:
  GROUP_C:
    const: IFP
  TXT:
    alias: [text]
    transform: to_text
require:
  fields: [TXT]
body:
  fields: [TXT]
  split: true
"""

def _write_rule(folder: Path, name: str, doc_type: str | None = None, extra: str = "") -> Path:
    """`custom_field_<name>.yaml` — 최상위 `doc_type:`(기본 name)으로 등록한 RULE."""
    path = folder / f"custom_field_{name}.yaml"
    path.write_text(RULE.replace("schema: v2\n", f"schema: v2\ndoc_type: {doc_type or name}\n") + extra, encoding="utf-8")
    return path


@pytest.fixture
def acts(tmp_path, monkeypatch):
    """기본 activity parse·chunk 와, parse 를 복제한 parse_tour(복제 때 card·music_ai 규칙 파일이 따라온다)."""
    from genon.preprocessor.activities.__main__ import new_activity

    root = tmp_path / "activities"
    for slug in ("parse", "chunk"):
        (root / slug).mkdir(parents=True)
        (root / slug / "processor.py").write_text(f"# {slug}\nclass DocumentProcessor: ...\n", encoding="utf-8")
        (root / slug / "config.yaml").write_text(CONFIG if slug == "parse" else "output: {}\n", encoding="utf-8")
    for doc_type in ("card", "music_ai"):
        _write_rule(root / "parse", doc_type)
    monkeypatch.delenv("GENOS_RESOURCE_DIR", raising=False)
    new_activity("parse", "parse_tour", activities_dir=root)
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _edit_config(root: Path, activity: str, old: str, new: str) -> None:
    path = root / activity / "config.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_list_reads_rule_file_registrations(acts):
    """규칙 파일 하나의 doc_type 마다 한 항목(파일 이름 순). doc_type 이 없는 규칙 파일은 등록이 아니다."""
    folder = acts / "parse"
    _write_rule(folder, "card", "[Card, card_new]")
    (folder / "custom_field_music_ai.yaml").write_text("schema: v2\ndoc_type: music_ai\n", encoding="utf-8")
    (folder / "custom_field_orphan.yaml").write_text(RULE, encoding="utf-8")
    described = "모니모 뮤직 AI 플레이리스트 문구 JSON 레코드"
    common = {"enable": True, "registered_in": "rule_file"}

    assert _doc_types.list_doc_types("parse", acts) == {"activity": "parse", "unknown_doc_type": "fail", "doc_types": [
        {"doc_type": "card", "config_file": "custom_field_card.yaml", "description": described, **common,
         "removable": False, "copyable": True},
        {"doc_type": "card_new", "config_file": "custom_field_card.yaml", "description": described, **common,
         "removable": False, "copyable": True},
        {"doc_type": "music_ai", "config_file": "custom_field_music_ai.yaml", "description": None, **common,
         "removable": True, "copyable": True},
    ]}
    # 복제한 activity 는 복제 시점의 규칙 파일을 그대로 가진다
    assert [d["doc_type"] for d in _doc_types.list_doc_types("parse_tour", acts)["doc_types"]] == ["card", "music_ai"]


def _flags(root, activity):
    return {d["doc_type"]: (d["removable"], d["copyable"])
            for d in _doc_types.list_doc_types(activity, root)["doc_types"]}


def test_list_flags_agree_with_remove_and_add(acts):
    """`removable`·`copyable` 은 `remove`·`add --from` 의 실제 결과와 같다(#756)."""
    folder = acts / "parse"
    # 규칙 파일의 doc_type 을 여러 줄 목록으로 적으면 복사본에 doc_type 한 줄을 적을 수 없다 — add --from 이 config_invalid
    (folder / "custom_field_tour_list.yaml").write_text(
        RULE.replace("schema: v2\n", "schema: v2\ndoc_type:\n  - tour_list\n"), encoding="utf-8")
    _write_rule(folder, "music_ai_notice", "music_ai")          # 같은 doc_type 의 두 번째 규칙 파일 — add --from 거부

    assert _flags(acts, "parse") == {
        "card": (True, True),
        "music_ai": (True, False),
        "tour_list": (True, False),
    }
    # 판정이 명령 결과와 같은지 실제로 부른다(파일이 바뀌므로 맨 끝에서)
    for doc_type, (removable, copyable) in _flags(acts, "parse").items():
        try:
            _doc_types.add_doc_type("probe_copy", doc_type, "parse", activities_dir=acts)
            copied = True
            _doc_types.remove_doc_type("probe_copy", "parse", activities_dir=acts)
        except DocTypeError:
            copied = False
        assert copied is copyable, doc_type
    for doc_type, (removable, _) in _flags(acts, "parse").items():
        try:
            _doc_types.remove_doc_type(doc_type, "parse", activities_dir=acts)
            removed = True
        except DocTypeError:
            removed = False
        assert removed is removable, doc_type


def _twice(root):
    _write_rule(root / "parse", "music_ai_notice", "MUSIC_AI")


def _twice_one_broken(root):
    _write_rule(root / "parse", "music_ai_notice", "music_ai", extra="no_such_key: 1\n")


def _unknown_key(root):
    _write_rule(root / "parse", "music_ai", extra="no_such_key: 1\n")


@pytest.mark.parametrize("name, break_it, valid, expected", [
    ("Music_AI", None, True, [("registered", "pass", None), ("block", "pass", None), ("config_file", "pass", None)]),
    ("tour_blog", None, False,
     [("registered", "fail", "not_registered"), ("block", "skip", None), ("config_file", "skip", None)]),
    # 같은 doc_type 을 규칙 파일 여럿이 등록하면 모두 적용된다 — 파일마다 검사하고 첫 실패를 보인다
    ("music_ai", _twice, True,
     [("registered", "pass", None), ("block", "pass", None), ("config_file", "pass", None)]),
    ("music_ai", _twice_one_broken, False,
     [("registered", "pass", None), ("block", "pass", None), ("config_file", "fail", "config_invalid")]),
    ("music_ai", _unknown_key, False,
     [("registered", "pass", None), ("block", "pass", None), ("config_file", "fail", "config_invalid")]),
])
def test_validate_reports_each_step_without_raising_or_writing(acts, name, break_it, valid, expected):
    if break_it:
        break_it(acts)
    before = _snapshot(acts)

    result = _doc_types.validate_doc_type(name, "parse", acts)

    assert (result["valid"], result["doc_type"]) == (valid, name.lower())
    assert [(s["step"], s["status"], s.get("reason")) for s in result["steps"]] == expected
    assert all(bool(s.get("message")) == (s["status"] in ("fail", "warn")) for s in result["steps"])
    assert _snapshot(acts) == before


def test_add_creates_rule_file_with_doc_type_and_leaves_config_untouched(acts):
    """`add` 는 규칙 파일 하나만 만든다 — `config.yaml` 을 고치지 않으므로 기본 activity parse 에도 등록된다(#748)."""
    before = _snapshot(acts)

    data, files = _doc_types.add_doc_type("tour_blog", "music_ai", "parse", title="여행 블로그 글", activities_dir=acts)

    folder = acts / "parse"
    assert data == {"doc_type": "tour_blog", "activity": "parse"}
    assert files == [folder / "custom_field_tour_blog.yaml"]
    # 규칙 파일: 첫 줄 주석이 --title 로 바뀌고 `schema:` 아래에 doc_type 한 줄이 늘 뿐, 나머지는 원본과 같다
    first, _, rest = (folder / "custom_field_tour_blog.yaml").read_text(encoding="utf-8").partition("\n")
    assert first == "# 문서 유형 tour_blog(여행 블로그 글)의 custom_fields 설정"
    assert rest == RULE.partition("\n")[2].replace("schema: v2\n", "schema: v2\ndoc_type: tour_blog\n")
    # 그 밖의 파일(config.yaml 포함)은 그대로이고, 새 등록은 검사를 통과한다
    after = _snapshot(acts)
    assert {k: v for k, v in after.items() if k != "parse/custom_field_tour_blog.yaml"} == before
    assert _doc_types.validate_doc_type("tour_blog", "parse", acts)["valid"] is True
    assert _doc_types.list_doc_types("parse", acts)["doc_types"][-1] == {
        "doc_type": "tour_blog", "config_file": "custom_field_tour_blog.yaml", "enable": True,
        "description": "문서 유형 tour_blog(여행 블로그 글)의 custom_fields 설정",
        "registered_in": "rule_file", "removable": True, "copyable": True}

    # 규칙 파일로 등록한 doc_type 을 --from 으로 쓰면 복사본의 doc_type 줄만 새 이름으로 바뀐다
    _doc_types.add_doc_type("tour_guide", "tour_blog", "parse", activities_dir=acts)
    assert (folder / "custom_field_tour_guide.yaml").read_text(encoding="utf-8") == \
        (folder / "custom_field_tour_blog.yaml").read_text(encoding="utf-8").replace(
            "doc_type: tour_blog\n", "doc_type: tour_guide\n")


def _broken_config(root):
    (root / "parse_tour" / "config.yaml").write_text("enrichment: [\n", encoding="utf-8")


def _leftover_block(root):
    """custom_fields 항목이 남은 설정은 worker 가 기동하지 못한다 — 명령도 거부한다."""
    _edit_config(root, "parse_tour", "  - toc:\n", "  - custom_fields: {doc_type: card, config_file: custom_field_card.yaml}\n  - toc:\n")


def _two_sources(root):
    _write_rule(root / "parse_tour", "music_ai_notice", "music_ai")


def _target_exists(root):
    (root / "parse_tour" / "custom_field_tour_blog.yaml").write_text(RULE, encoding="utf-8")


@pytest.mark.parametrize("name, origin, activity, break_it, reason", [
    ("tour_blog", "music_ai", "parse_nope", None, "activity_not_found"),
    ("tour_blog", "music_ai", "../parse", None, "activity_not_found"),
    ("tour_blog", "music_ai", "chunk", None, "not_parse_activity"),
    ("Tour-Blog", "music_ai", "parse_tour", None, "invalid_name"),
    ("1tour", "music_ai", "parse_tour", None, "invalid_name"),     # 소문자로 시작해야 한다
    ("_x", "music_ai", "parse_tour", None, "invalid_name"),
    ("tour_blog", "faq", "parse_tour", None, "source_not_found"),
    ("tour_blog", "music_ai", "parse_tour", _target_exists, "config_file_exists"),
    ("tour_blog", "music_ai", "parse_tour", _broken_config, "config_invalid"),
    ("tour_blog", "music_ai", "parse_tour", _leftover_block, "config_invalid"),
    ("tour_blog", "music_ai", "parse_tour", _two_sources, "multiple_rule_files"),
])
def test_add_rejects_with_reason_and_changes_no_file(acts, name, origin, activity, break_it, reason):
    if break_it:
        break_it(acts)
    before = _snapshot(acts)

    with pytest.raises(DocTypeError) as info:
        _doc_types.add_doc_type(name, origin, activity, title="설명", activities_dir=acts)

    assert info.value.detail == {"reason": reason}
    assert _snapshot(acts) == before


def test_add_of_registered_name_fails_with_registration_state(acts):
    """복제 때 따라온 music_ai 를 다시 add 하면 거부하고, validate 와 같은 검사 결과를 메시지 첫 줄과 detail.steps 에 싣는다."""
    before = _snapshot(acts)
    with pytest.raises(DocTypeError) as info:
        _doc_types.add_doc_type("music_ai", "card", "parse_tour", activities_dir=acts)
    assert str(info.value) == "doc_type=music_ai 이미 등록됨: config_file=custom_field_music_ai.yaml, 등록 상태 정상"
    assert info.value.detail == {"reason": "already_registered",
                                 "steps": _doc_types.validate_doc_type("music_ai", "parse_tour", acts)["steps"]}
    assert [s["status"] for s in info.value.detail["steps"]] == ["pass", "pass", "pass"]
    assert _snapshot(acts) == before

    _write_rule(acts / "parse_tour", "music_ai", extra="no_such_key: 1\n")
    with pytest.raises(DocTypeError) as info:
        _doc_types.add_doc_type("music_ai", "card", "parse_tour", activities_dir=acts)
    first, second = str(info.value).split("\n", 1)                 # 검사에 실패한 등록은 첫 줄이 알리고 그 뒤가 사유다
    assert first.endswith("등록 상태 확인 필요")
    assert second == info.value.detail["steps"][-1]["message"]


def _run_cli(capsys, *argv) -> tuple[int, dict]:
    cli = importlib.import_module("genon.preprocessor.activities.__main__")
    code = cli.main(["doc-types", *argv])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith(cli.RESULT_PREFIX)
    return code, json.loads(last[len(cli.RESULT_PREFIX):])


def test_cli_result_line_carries_reason_in_error_detail(acts, monkeypatch, capsys):
    """결과 줄 계약: 거부는 exit 1 · `error.detail.reason`, 검사 실패는 exit 0 · `data.valid: false`."""
    monkeypatch.setattr(_folders, "ACTIVITIES_DIR", acts)
    before = _snapshot(acts)

    code, result = _run_cli(capsys, "add", "--name", "tour_blog", "--from", "music_ai", "--activity", "chunk")
    assert code == 1
    assert {k: result[k] for k in ("ok", "stage", "activity", "command")} == {
        "ok": False, "stage": None, "activity": "chunk", "command": "doc-types"}
    assert {k: result["error"][k] for k in ("type", "non_retryable", "detail")} == {
        "type": "DocTypeError", "non_retryable": True, "detail": {"reason": "not_parse_activity"}}
    assert "reason_code" not in result["error"]

    code, result = _run_cli(capsys, "validate", "--name", "tour_blog")
    assert (code, result["ok"], result["command"], result["data"]["valid"]) == (0, True, "doc-types", False)

    code, result = _run_cli(capsys, "add", "--name", "tour_blog", "--from", "music_ai", "--activity", "parse_tour",
                            "--title", "두\n줄")
    assert (code, result["error"]["type"]) == (1, "_UsageError")
    assert _snapshot(acts) == before

    code, result = _run_cli(capsys, "add", "--name", "tour_blog", "--from", "music_ai", "--activity", "parse_tour")
    assert (code, result["stage"], result["activity"]) == (0, None, "parse_tour")
    assert result["data"]["doc_type"] == "tour_blog"
    assert [Path(f).name for f in result["data"]["files"]] == ["custom_field_tour_blog.yaml"]


@pytest.mark.parametrize("argv", [
    ("add", "--name", "tour_blog", "--from", "music_ai"),                                    # 필수 인자 누락(argparse)
    ("update", "--name", "tour_blog"),                                                       # 모르는 action(argparse)
    ("add", "--name", "tour_blog", "--from", "music_ai", "--activity", "parse_tour", "--title", "두\n줄"),
])
def test_cli_usage_error_carries_command_and_reason(acts, monkeypatch, capsys, argv):
    """인자 오류도 결과 줄에 `command` 와 `error.detail.reason = usage_error` 를 싣는다. 다른 명령은 그대로다."""
    monkeypatch.setattr(_folders, "ACTIVITIES_DIR", acts)
    code, result = _run_cli(capsys, *argv)
    assert (code, result["ok"], result["stage"], result["command"]) == (1, False, None, "doc-types")
    assert {k: result["error"][k] for k in ("type", "non_retryable", "detail")} == {
        "type": "_UsageError", "non_retryable": False, "detail": {"reason": "usage_error"}}

    cli = importlib.import_module("genon.preprocessor.activities.__main__")
    assert cli.main(["remove"]) == 1                                                         # 다른 명령의 인자 오류
    other = json.loads(capsys.readouterr().out.strip().splitlines()[-1][len(cli.RESULT_PREFIX):])
    assert "detail" not in other["error"] and "command" not in other


# ── remove (#739) ────────────────────────────────────────────────────────────

def test_remove_undoes_add_exactly(acts):
    """add 한 doc_type 을 remove 하면 규칙 파일만 지워져 add 전과 같아진다 — 기본 activity parse 에서도 같다."""
    before = _snapshot(acts)
    _doc_types.add_doc_type("tour_blog", "music_ai", "parse", activities_dir=acts)

    data, files = _doc_types.remove_doc_type("tour_blog", "parse", activities_dir=acts)

    assert data == {"doc_type": "tour_blog", "activity": "parse"}
    assert files == [acts / "parse" / "custom_field_tour_blog.yaml"]
    assert _snapshot(acts) == before


def test_remove_deletes_every_rule_file_of_the_doc_type(acts):
    """같은 doc_type 을 등록한 규칙 파일을 모두 지운다. config.yaml 과 다른 doc_type 의 규칙 파일은 그대로다."""
    notice = _write_rule(acts / "parse_tour", "music_ai_notice", "music_ai")
    before = _snapshot(acts)

    data, files = _doc_types.remove_doc_type("music_ai", "parse_tour", activities_dir=acts)

    assert files == [acts / "parse_tour" / "custom_field_music_ai.yaml", notice]
    assert {k: v for k, v in _snapshot(acts).items()} == {
        k: v for k, v in before.items()
        if k not in ("parse_tour/custom_field_music_ai.yaml", "parse_tour/custom_field_music_ai_notice.yaml")}


@pytest.mark.parametrize("name, activity, break_it, reason", [
    ("tour_blog", "parse_tour", None, "not_registered"),
    ("card", "chunk", None, "not_parse_activity"),
    ("card", "parse_nope", None, "activity_not_found"),
    ("card", "parse_tour", "[card, cash]", "shared_block"),
])
def test_remove_rejects_with_reason_and_changes_no_file(acts, name, activity, break_it, reason):
    if break_it:
        _write_rule(acts / "parse_tour", "card", break_it)
    before = _snapshot(acts)
    with pytest.raises(DocTypeError) as exc:
        _doc_types.remove_doc_type(name, activity, activities_dir=acts)
    assert exc.value.detail["reason"] == reason
    assert _snapshot(acts) == before


def test_cli_remove_result_line(acts, monkeypatch, capsys):
    monkeypatch.setattr(_folders, "ACTIVITIES_DIR", acts)
    _doc_types.add_doc_type("tour_blog", "music_ai", "parse_tour", activities_dir=acts)
    code, result = _run_cli(capsys, "remove", "--name", "tour_blog", "--activity", "parse_tour")
    assert (code, result["ok"], result["command"], result["activity"]) == (0, True, "doc-types", "parse_tour")
    assert [Path(f).name for f in result["data"]["files"]] == ["custom_field_tour_blog.yaml"]
    code, result = _run_cli(capsys, "remove", "--name", "tour_blog", "--activity", "parse_tour")
    assert (code, result["error"]["detail"]) == (1, {"reason": "not_registered"})


# ── rename (#808) ────────────────────────────────────────────────────────────

def test_rename_rewrites_doc_type_in_place(acts, monkeypatch, capsys):
    """그 doc_type 을 등록한 규칙 파일마다 `doc_type:` 값만 바꾼다. 관례 이름의 파일은 새 이름으로 옮기고,
    다른 이름의 파일과 목록 등록 파일은 이름을 두며, 목록에서는 그 원소만 바꾼다. 새 파일은 생기지 않는다."""
    monkeypatch.setattr(_folders, "ACTIVITIES_DIR", acts)
    folder = acts / "parse_tour"
    notice = _write_rule(folder, "music_ai_notice", "music_ai")
    bundle = _write_rule(folder, "bundle", "[card_extra, music_ai]")
    before = _snapshot(acts)

    code, result = _run_cli(capsys, "rename", "--name", "music_ai", "--to", "music_list", "--activity", "parse_tour")

    assert (code, result["ok"], result["command"]) == (0, True, "doc-types")
    assert {k: result["data"][k] for k in ("doc_type", "renamed_to", "activity")} == {
        "doc_type": "music_ai", "renamed_to": "music_list", "activity": "parse_tour"}
    assert [Path(f).name for f in result["data"]["files"]] == [
        "custom_field_bundle.yaml", "custom_field_music_ai.yaml", "custom_field_music_list.yaml",
        "custom_field_music_ai_notice.yaml"]
    after = _snapshot(acts)
    rel = "parse_tour/custom_field_"
    assert after[f"{rel}music_list.yaml"] == before[f"{rel}music_ai.yaml"].replace(b"doc_type: music_ai\n",
                                                                                   b"doc_type: music_list\n")
    assert after[f"{rel}music_ai_notice.yaml"] == notice.read_bytes() == before[f"{rel}music_ai_notice.yaml"].replace(
        b"doc_type: music_ai\n", b"doc_type: music_list\n")
    assert after[f"{rel}bundle.yaml"] == bundle.read_bytes() == before[f"{rel}bundle.yaml"].replace(
        b"doc_type: [card_extra, music_ai]\n", b"doc_type: [card_extra, music_list]\n")
    changed = {f"{rel}music_ai.yaml", f"{rel}music_list.yaml", f"{rel}music_ai_notice.yaml", f"{rel}bundle.yaml"}
    assert {k: v for k, v in after.items() if k not in changed} == {k: v for k, v in before.items() if k not in changed}


def _multiline_list(root):
    (root / "parse_tour" / "custom_field_music_ai.yaml").write_text(
        RULE.replace("schema: v2\n", "schema: v2\ndoc_type:\n  - music_ai\n"), encoding="utf-8")


def _unregistered_target_file(root):
    (root / "parse_tour" / "custom_field_music_list.yaml").write_text(RULE, encoding="utf-8")


@pytest.mark.parametrize("name, to, activity, break_it, reason", [
    ("tour_blog", "music_list", "parse_tour", None, "not_registered"),
    ("music_ai", "card", "parse_tour", None, "already_registered"),
    ("music_ai", "Music-List", "parse_tour", None, "invalid_name"),
    ("music_ai", "music_list", "parse_tour", _unregistered_target_file, "config_file_exists"),
    # 여러 줄 목록은 줄 하나로 고칠 수 없다 — 다른 규칙 파일도 바꾸지 않는다
    ("music_ai", "music_list", "parse_tour", _multiline_list, "config_invalid"),
])
def test_rename_rejects_with_reason_and_changes_no_file(acts, name, to, activity, break_it, reason):
    if break_it:
        break_it(acts)
    _write_rule(acts / "parse_tour", "music_ai_notice", "music_ai")
    before = _snapshot(acts)
    with pytest.raises(DocTypeError) as exc:
        _doc_types.rename_doc_type(name, to, activity, activities_dir=acts)
    assert exc.value.detail["reason"] == reason
    assert _snapshot(acts) == before


# ── add --from-activity · new --doc-type (#822) — 복제한 parse activity 에 원하는 doc_type 규칙 파일만 둔다 ─────────────

def test_add_from_activity_copies_rule_file_of_another_activity(acts):
    """다른 parse activity 에 등록된 규칙 파일을 가져온다 — 같은 이름이면 본문이 원본과 같다."""
    (acts / "parse_tour" / "custom_field_card.yaml").unlink()
    before = _snapshot(acts)

    data, files = _doc_types.add_doc_type("card", "card", "parse_tour", activities_dir=acts, from_activity="parse")

    assert data == {"doc_type": "card", "activity": "parse_tour"}
    assert files == [acts / "parse_tour" / "custom_field_card.yaml"]
    after = _snapshot(acts)
    assert after["parse_tour/custom_field_card.yaml"] == after["parse/custom_field_card.yaml"]
    assert {k: v for k, v in after.items() if k != "parse_tour/custom_field_card.yaml"} == before
    assert _doc_types.validate_doc_type("card", "parse_tour", acts)["valid"] is True

    # 다른 이름으로 가져오면 doc_type 줄만 새 이름이다
    _doc_types.add_doc_type("card_vip", "card", "parse_tour", activities_dir=acts, from_activity="parse")
    assert (acts / "parse_tour" / "custom_field_card_vip.yaml").read_bytes() == \
        after["parse/custom_field_card.yaml"].replace(b"doc_type: card\n", b"doc_type: card_vip\n")


@pytest.mark.parametrize("name, origin, from_activity, reason", [
    ("faq", "faq", "parse", "source_not_found"),              # 원본 activity 에 등록 없음
    ("card", "card", "parse_nope", "activity_not_found"),
])
def test_add_from_activity_rejects_with_reason_and_changes_no_file(acts, name, origin, from_activity, reason):
    (acts / "parse_tour" / "custom_field_card.yaml").unlink()
    before = _snapshot(acts)

    with pytest.raises(DocTypeError) as info:
        _doc_types.add_doc_type(name, origin, "parse_tour", activities_dir=acts, from_activity=from_activity)

    assert info.value.detail["reason"] == reason
    assert _snapshot(acts) == before


def _rule_names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("custom_field_*.yaml"))


@pytest.mark.parametrize("doc_types, copied, missing", [
    (["music_ai"], ["custom_field_music_ai.yaml"], []),
    ([" Music_AI "], ["custom_field_music_ai.yaml"], []),                         # 이름 비교는 worker 와 같다
    (["card", "music_ai"], ["custom_field_card.yaml", "custom_field_music_ai.yaml"], []),
    (["card", "faq"], ["custom_field_card.yaml"], ["faq"]),                        # 원본에 없는 doc_type 은 규칙 파일 없이
    (["pair_a", "pair_b"], ["custom_field_pair.yaml"], []),                        # 파일 하나의 doc_type 을 모두 지정
    (["music_ai", "music_ai"], ["custom_field_music_ai.yaml", "custom_field_music_ai_notice.yaml"], []),  # 같은 doc_type 의 파일 여럿
])
def test_new_with_doc_types_copies_only_their_rule_files(acts, doc_types, copied, missing):
    from genon.preprocessor.activities.__main__ import missing_doc_types, new_activity

    folder = acts / "parse"
    _write_rule(folder, "pair", "[pair_a, pair_b]")
    (folder / "custom_field_draft.yaml").write_text(RULE, encoding="utf-8")        # doc_type 줄 없음 — 등록이 아니다
    (folder / "prompt_x.md").write_text("prompt\n", encoding="utf-8")
    if "custom_field_music_ai_notice.yaml" in copied:
        _write_rule(folder, "music_ai_notice", "music_ai")
    before = _snapshot(acts)

    files = new_activity("parse", "parse_one", activities_dir=acts, doc_types=doc_types)

    assert _rule_names(acts / "parse_one") == copied
    assert sorted(Path(f).name for f in files) == sorted(["config.yaml", "processor.py", "prompt_x.md", *copied])
    assert missing_doc_types("parse_one", doc_types, activities_dir=acts) == missing
    assert {k: v for k, v in _snapshot(acts).items() if not k.startswith("parse_one/")} == before


@pytest.mark.parametrize("origin, slug, doc_types, needle", [
    ("parse", "parse_one", ["pair_a"], "일부만 지정됨"),
    ("parse", "parse_one", ["card", " "], "값이 비어 있음"),
    ("chunk", "chunk_one", ["card"], "parse 단계가 아님"),
])
def test_new_with_doc_types_rejects_and_creates_nothing(acts, origin, slug, doc_types, needle):
    from genon.preprocessor.activities.__main__ import new_activity

    _write_rule(acts / "parse", "pair", "[pair_a, pair_b]")
    before = _snapshot(acts)

    with pytest.raises(ValueError, match=needle):
        new_activity(origin, slug, activities_dir=acts, doc_types=doc_types)

    assert _snapshot(acts) == before
    assert not (acts / slug).exists()


def test_cli_new_reports_missing_doc_types_only_when_doc_type_given(acts, monkeypatch, capsys):
    monkeypatch.setattr(_folders, "ACTIVITIES_DIR", acts)
    cli = importlib.import_module("genon.preprocessor.activities.__main__")

    def run(*argv):
        code = cli.main(["new", "--from", "parse", *argv])
        last = capsys.readouterr().out.strip().splitlines()[-1]
        return code, json.loads(last[len(cli.RESULT_PREFIX):])

    code, result = run("--slug", "parse_one", "--doc-type", "card", "--doc-type", "faq")
    assert code == 0 and result["command"] == "new" and result["activity"] == "parse_one"
    assert result["data"]["missing_doc_types"] == ["faq"]
    assert _rule_names(acts / "parse_one") == ["custom_field_card.yaml"]

    code, result = run("--slug", "parse_all")                                      # 주지 않으면 지금처럼 전부 복사
    assert code == 0 and "missing_doc_types" not in result["data"]
    assert _rule_names(acts / "parse_all") == ["custom_field_card.yaml", "custom_field_music_ai.yaml"]

    code, result = _run_cli(capsys, "add", "--name", "music_ai", "--from", "music_ai", "--from-activity", "parse",
                            "--activity", "parse_one")
    assert code == 0 and result["data"]["doc_type"] == "music_ai"
    assert _rule_names(acts / "parse_one") == ["custom_field_card.yaml", "custom_field_music_ai.yaml"]
