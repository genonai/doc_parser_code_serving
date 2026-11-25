"""배포 전 custom_fields 설정 점검 — 코드를 올리기 **전에** 현장 설정을 검사한다.

## 왜 필요한가

이번 변경으로 설정 오기입이 기동 실패가 된다(예전에는 조용히 무시됐다). 저장소 안의
`resource/` 는 전수 확인했지만, 현장에서 손댄 설정이 있다면 그건 배포해 봐야 안다 —
그 시점에 알면 이미 서비스가 안 뜬다.

이 스크립트는 **파싱과 LLM 호출 없이 yaml 만 읽어** 그 위험을 미리 드러낸다.
판정은 `processing/enrichment/config_schema.py` 를 그대로 import 해서 쓰므로 검증기와
규칙이 갈리지 않는다(스크립트가 규칙을 다시 구현하면 반드시 갈린다).

## 무엇을 잡나

1. **기동을 막는 것** — 이 extractor 가 읽지 않는 키(오타 포함)
2. **제거된 키** — `nulls` / `json_text_fields` / extractor 별칭 4종
3. **청크 본문이 바뀌는 것** — `column_map` 에도 `field_labels` 에도 없는 필드를
   `text_fields` 에 쓴 경우. 예전에는 목표필드명이 라벨로 붙었고 이제는 값만 나간다.
   본문이 바뀌면 임베딩이 바뀌므로 재색인 판단이 필요하다.
4. **없는 모델 프리셋을 부르는 것** — `model_preset:` 이 가리키는 이름이 그 프로세서
   config 의 `model_presets` 에 없는 경우. 자식 custom_field yaml 의 참조도 함께 본다.
5. **기동 시 컴파일에서 막히는 transform** — 없는 변환기·쓸 수 없는 인자(오타 포함)·
   잘못된 정규식·체인 중간의 `to_json`. 기동과 같은 `compile_transforms` 를 실행한다.
   매퍼·enricher 생성자가 이어서 실행하는 검증도 같은 함수로 실행한다 — template·pack 의
   참조 필드, 본문에 넣은 pack 필드, html 선택자 문법, 목표필드명 규칙(`check_startup_compile`).
6. **텍스트 표 설명 블록의 오기입** — `table_text_description` 과 그 `rag`·`skip` 의 모르는
   키, 잘못된 `rag.search_terms`·`skip` 값(경고). 프로세서 공통·custom_field yaml
   을 따로 본다. 기동은 같은 판정으로 경고만 남기고 그 값을 무시한다.
7. **파서·청커의 표 형식 불일치** — 같은 폴더의 두 설정에서 `output.table_format` 이 다른
   경우(경고). 레코드형 문서는 파서 값, 일반 문서는 청커 값으로 표가 나가 모양이 갈린다.

## 쓰는 법

    ./precheck_custom_fields.sh                        # 저장소 resource/
    ./precheck_custom_fields.sh /path/to/site/resource # 현장 설정 디렉터리

문제가 하나라도 있으면 비-0 으로 끝난다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from genon.preprocessor.processing.common import config_parse as cp  # noqa: E402
from genon.preprocessor.processing.common import model_preset as mp  # noqa: E402
from genon.preprocessor.processing.enrichment import config_schema as cs  # noqa: E402
from genon.preprocessor.processing.enrichment import config_v2 as cv2  # noqa: E402
from genon.preprocessor.processing.enrichment import html_select  # noqa: E402
from genon.preprocessor.processing.enrichment.enrichment_config import (  # noqa: E402
    reject_registration_blocks,
    rule_file_blocks,
)
from genon.preprocessor.processing.enrichment.tabular_custom_fields import (  # noqa: E402
    compile_derive,
    compile_meta_exclude,
    compile_pack,
    compile_sheets,
    compile_transforms,
    meta_exclude_unused_note,
    validate_custom_field_config,
)

# 이번 정리에서 없앤 키 → 대신 쓸 것.
REMOVED_KEYS = {
    "nulls": "defaults 에 `필드: null` 로 적는다(결과가 같다)",
    "json_text_fields": "`transform: to_text` 로 옮긴다(값 종류를 자동 판별한다)",
    "text_from": "같은 alias 를 목표필드에 한 번 더 붙이고 `transform: to_text` 를 건다",
    "html_text_fields": "같은 alias 를 목표필드에 한 번 더 붙이고 `transform: to_text` 를 건다",
}

PROCESSOR_CONFIGS = (
    "config.yaml",                     # 액티비티 폴더(activities/<slug>/·사이트 activities/<slug>/)의 설정
    "parse_config.yaml",
    "parse_config_simple.yaml",
    "intelligent_processor_config.yaml",
    "convert_processor_config.yaml",
    "chunk_config.yaml",
    "chunk_config_simple.yaml",
    "attachment_processor_config.yaml",
)
# custom_fields enricher 를 만들지 않는 processor 설정. 같은 폴더의 규칙 파일 등록이 이 설정에는 적용되지 않으므로
# 규칙 파일의 `model_preset:` 을 이 설정의 프리셋으로 풀어 보지 않는다(청커는 metadata 설정만, 첨부는 enrichment 를 읽지 않음).
NO_CUSTOM_FIELDS_CONFIGS = frozenset({
    "chunk_config.yaml", "chunk_config_simple.yaml", "attachment_processor_config.yaml",
})


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - 어떤 파싱 실패든 그대로 알린다
        raise SystemExit(f"[치명] {path} 를 읽을 수 없습니다: {exc}")


def registered_blocks(root: Path) -> list[tuple[str, dict, dict]]:
    """(프로세서 config 이름, 규칙 파일 등록 `{doc_type, config_file}`, 그 config 의 모델 프리셋) 목록.

    doc_type 등록은 규칙 파일 최상위의 `doc_type:` 한 가지다(#798). 기동할 때 그 폴더를 읽는 processor 설정마다
    등록되고 프리셋도 설정마다 다르므로, 설정 파일마다 한 번씩 싣는다. processor 설정에 등록 블록이 남아 있어
    기동이 실패하는 설정은 기동과 같은 함수(`reject_registration_blocks`)가 알린다.

    프리셋을 함께 들고 다니는 이유는 자식 설정 검증 때문이다 — 자식 yaml 의
    `model_preset:` 은 기동 시 이 프리셋으로 펼쳐지므로, 점검도 같은 재료로 해야 한다.
    """
    blocks: list[tuple[str, dict, dict]] = []
    for name in PROCESSOR_CONFIGS:
        path = root / name
        if not path.exists():
            continue
        cfg = load_yaml(path)
        # 형식 오류는 check_model_presets 가 보고한다. 여기서는 모을 수 있는 만큼만 모은다.
        presets = cp.collect_model_presets(cfg, str(path), strict=False)
        own = [item.get("custom_fields") for item in (cfg.get("enrichment") or [])
               if isinstance(item, dict) and isinstance(item.get("custom_fields"), dict)]
        try:
            reject_registration_blocks(own)
            found = rule_file_blocks(root, {})
        except ValueError as exc:
            raise SystemExit(f"[치명] {name}: {exc}")
        if name in NO_CUSTOM_FIELDS_CONFIGS:
            continue
        blocks.extend((name, {k: block[k] for k in ("doc_type", "config_file")}, presets) for block in found)
    return blocks


def _derive_extractor(path: Path) -> str | None:
    """설정 파일의 `source.kind` 에서 extractor 를 유도한다(못 하면 None).

    판정은 `config_v2.normalize` 에 맡긴다 — 규칙을 여기 다시 구현하면 반드시 갈린다.
    읽을 수 없거나 v2 가 아니면 None 이고, 그 오류는 아래 본 검사에서 제대로 보고된다.
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict) or not cv2.is_v2(loaded):
            return None
        _internal, extractor = cv2.normalize(loaded, label=str(path.name))
    except Exception:  # noqa: BLE001 - 어떤 실패든 "유도 못 함"으로 흡수한다
        return None
    return extractor


def check_block(
    source: str, block: dict, root: Path, seen_files: set[str],
    presets: dict | None = None,
) -> list[str]:
    """규칙 파일 등록 하나(`{doc_type, config_file}`)와 그 규칙 파일을 검사한다.

    같은 규칙 파일이 그 폴더를 읽는 processor 설정마다 등록되는 것이 정상이라 파일 단위 검사는
    `seen_files` 로 한 번만 한다.
    """
    problems: list[str] = []
    presets = presets if isinstance(presets, dict) else {}
    where = f"{source} [doc_type={block.get('doc_type')}]"
    # 기동 시 `custom_fields_extractor` 와 같이 config_file 의 source.kind 에서 유도한다.
    extractor = _derive_extractor(root / str(block.get("config_file") or "")) or "llm"

    config_file = block.get("config_file")
    if not config_file:
        return problems
    path = root / str(config_file)
    if not path.exists():
        problems.append(f"[기동실패] {where}: config_file '{config_file}' 이 없습니다.")
        return problems

    if str(config_file) in seen_files:
        return problems
    seen_files.add(str(config_file))

    cfg = load_yaml(path)
    label = f"{config_file}"
    # 없어진 키는 **번역 전** 원본에서 본다. 번역기가 먼저 "모르는 키"로 막아 버리면
    # 무엇으로 갈아타야 하는지 알려 줄 기회가 사라진다 — 안내가 필요한 쪽은 옛 설정이다.
    for key, hint in REMOVED_KEYS.items():
        if key in (cfg or {}):
            problems.append(f"[기동실패] {label}: `{key}` 는 없어졌습니다 → {hint}.")
    if problems:
        return problems

    if cfg and not cv2.is_v2(cfg):
        # 폐기된 v1 표기. 기동에서 막히므로 여기서도 같은 판정을 낸다.
        problems.append(
            f"[기동실패] {label}: 최상위에 `schema: v2` 가 없습니다. "
            f"v1 표기는 더 이상 지원하지 않습니다."
        )
        return problems
    if cfg:
        # 내부 형태로 번역된 뒤에야 extractor 지원키와 대조할 수 있다.
        # 번역 전 원본을 그대로 검사하면 v2 키가 전부 "모르는 키"로 잡힌다.
        #
        # 번역과 함께 `model_preset:` 도 편다. 기동은 같은 순서로 하므로, 여기서 안 펴면
        # 프리셋을 제대로 쓴 설정에서 model_preset 이 "모르는 키" 로 잡히는 오탐이 난다.
        try:
            cfg, _derived_extractor = cv2.load(cfg, label=label, presets=presets)
        except (cv2.ConfigV2Error, mp.ModelPresetError) as exc:
            problems.append(f"[기동실패] {exc}")
            return problems
    diagnosis = cs.diagnose_keys(cfg, extractor)
    if diagnosis:
        problems.append(f"[기동실패] {cs.format_diagnosis(label, diagnosis)}")
    for problem in cs.diagnose_table_text_description(cfg.get("table_text_description")):
        problems.append(f"[경고] {label} table_text_description: {problem}.")
    # transform 은 키 대조가 아니라 컴파일 단계에서 검증되므로 기동과 같은 함수를 실행한다.
    try:
        compile_transforms(cfg.get("transforms"), label=label, cfg=cfg)
    except ValueError as exc:
        problems.append(f"[기동실패] {exc}")

    problems.extend(check_startup_compile(label, cfg, extractor))

    problems.extend(check_body_label_change(label, cfg))
    return problems


# 생성자에서 `validate_custom_field_config` 를 부르는 extractor. llm·python·html_select 는
# enricher 가 맡고 이 검증을 부르지 않으므로, 여기서 부르면 기동은 뜨는 설정을 막는 오탐이 된다.
_VALIDATED_EXTRACTORS = {"tabular_mapping", "json_mapping", "json_semantic"}


def check_startup_compile(label: str, cfg: dict, extractor: str) -> list[str]:
    """매퍼·enricher 생성자가 기동 시 실행하는 검증을 같은 함수, 같은 조건으로 실행한다.

    키 대조와 transform 컴파일만 보면 template 의 없는 참조 필드, 본문에 넣은 pack 필드,
    html 선택자 문법 오류, 목표필드명 규칙 위반은 통과한다. 그런데 기동은 여기서 실패하므로
    점검과 기동의 판정이 갈린다. 규칙을 다시 구현하지 않고 기동의 함수를 그대로 부른다.
    """
    checks = [compile_derive, compile_pack, compile_meta_exclude]
    if extractor in _VALIDATED_EXTRACTORS:
        checks.insert(0, lambda c, *, label: validate_custom_field_config(
            c, label=label, extractor=extractor))
    if extractor == "html_select":
        checks.append(html_select.compile_selectors)
    if extractor == "tabular_mapping":
        checks.append(compile_sheets)
    problems: list[str] = []
    for check in checks:
        try:
            check(cfg, label=label)
        except ValueError as exc:
            problems.append(f"[기동실패] {exc}")
    # 기동은 이 안내를 그 설정으로 문서를 처리할 때만 남긴다(`warn_note_once`). 점검은 모든 설정을 본다.
    try:
        note = meta_exclude_unused_note(cfg, compile_meta_exclude(cfg, label=label), label=label)
    except ValueError:
        note = None                                   # 위에서 기동실패로 이미 알렸다
    if note:
        problems.append(f"[경고] {note}")
    return problems


def check_body_label_change(label: str, cfg: dict) -> list[str]:
    """청크 본문 라벨이 바뀌는 필드를 알린다(재색인 판단용).

    예전에는 `column_map` 에 없는 필드도 목표필드명이 라벨로 붙었다("SUMMARY_TEXT: …").
    이제는 이름이 없으면 값만 나가므로, 그런 필드가 본문에 있으면 청크 텍스트가 달라진다.
    """
    column_map = cfg.get("column_map")
    if not isinstance(column_map, dict) or not column_map:
        return []  # column_map 이 없는 경로는 예전에도 폴백하지 않았다
    raw_labels = cfg.get("field_labels")
    labels: dict = raw_labels if isinstance(raw_labels, dict) else {}
    raw_text_fields = cfg.get("text_fields")
    text_fields: list = raw_text_fields if isinstance(raw_text_fields, list) else []
    affected = [
        str(f) for f in text_fields
        if str(f) not in column_map and str(f) not in labels
    ]
    if not affected:
        return []
    return [
        f"[본문변화] {label}: {affected} 는 청크 본문에서 "
        f"`필드명: 값` → `값` 으로 바뀝니다. 임베딩이 달라지므로 재색인을 검토하거나 "
        f"field_labels 에 사람이 읽는 이름을 주세요."
    ]


def check_model_presets(root: Path) -> list[str]:
    """`model_presets` 정의와 그것을 부르는 `model_preset:` 참조를 대조한다.

    기동 시에는 `load_config` 가 같은 판정을 하고 없는 이름이면 서비스가 뜨지 않는다.
    여기서 미리 드러내 배포 전에 잡는다. 참조를 찾는 규칙은 `model_preset.iter_refs` 를
    그대로 쓴다 — 스크립트가 다시 구현하면 반드시 갈린다.

    규칙 파일(custom_field yaml)의 참조는 **그 폴더의 프로세서 config** 의 프리셋으로 푼다.
    규칙 파일에는 프리셋 정의가 없고, 최상위 `doc_type:` 으로 등록하면 그 폴더의 모든 프로세서 config 에
    등록되기 때문이다.
    """
    problems: list[str] = []
    for name in PROCESSOR_CONFIGS:
        path = root / name
        if not path.exists():
            continue
        cfg = load_yaml(path)
        # 프리셋은 기동과 같은 규칙으로 모은다(`model_presets_file` 로 지정한 파일 + 인라인).
        try:
            presets = cp.collect_model_presets(cfg, str(path), strict=True)
        except ValueError as exc:  # ModelPresetError 와 경로 범위 위반 모두 ValueError 다
            problems.append(f"[기동실패] {name}: {exc}")
            continue

        # 참조를 찾을 곳: 프로세서 config 자신 + 그 폴더에서 doc_type 을 등록한 규칙 파일들.
        targets: list[tuple[str, dict]] = [(name, cfg)]
        try:
            self_registered = [] if name in NO_CUSTOM_FIELDS_CONFIGS else cv2.rule_file_registrations(root)
        except ValueError:                  # 형식 오류는 registered_blocks 가 먼저 알린다
            self_registered = []
        for block in self_registered:
            child_name = block["config_file"]
            targets.append((f"{name} → {child_name}", load_yaml(root / child_name)))

        used: set[str] = set()
        for where, node in targets:
            for place, ref in mp.iter_refs(node):
                if not isinstance(ref, str) or not ref.strip():
                    problems.append(
                        f"[기동실패] {where} [{place}]: 프리셋 이름이 비어 있습니다."
                    )
                    continue
                ref = ref.strip()
                used.add(ref)
                if ref not in presets:
                    known = ", ".join(sorted(presets)) or "(정의된 프리셋 없음)"
                    problems.append(
                        f"[기동실패] {where} [{place}]: `{ref}` 프리셋이 "
                        f"{name} 의 `{mp.PRESETS_KEY}` 에 없습니다. 정의된 이름: {known}"
                    )

        # 공유 프리셋 파일(`model_presets_file`)은 여러 설정이 나눠 쓰므로 안 쓰는 이름이 있는 게
        # 정상이다. 이 설정에 직접 적은 프리셋만 본다.
        inline = cfg.get(mp.PRESETS_KEY) if isinstance(cfg.get(mp.PRESETS_KEY), dict) else {}
        unused = sorted(set(inline) - used)
        if unused:
            problems.append(f"[정보] {name}: 아무도 참조하지 않는 프리셋 {unused}")
        blocked = sorted({k for v in presets.values() if isinstance(v, dict) for k in v
                          if k in mp.BLOCKED_KEYS})
        if blocked:
            problems.append(
                f"[정보] {name}: 프리셋의 {blocked} 는 배선 키라 주입되지 않습니다 "
                f"(쓰는 블록에 직접 적으세요)."
            )
    return problems


# 같은 폴더에서 짝을 이루는 파서·청커 설정. 청크의 표 모양을 문서 종류마다 나눠 정한다.
TABLE_FORMAT_PAIRS = (
    ("parse_config.yaml", "chunk_config.yaml"),
    ("parse_config_simple.yaml", "chunk_config_simple.yaml"),
)


def check_table_text_blocks(root: Path) -> list[str]:
    """프로세서 설정의 공통 `table_text_description` 을 본다.

    custom_field yaml 쪽 블록은 `check_block` 이 번역한 설정으로 본다.
    """
    problems: list[str] = []
    for name in PROCESSOR_CONFIGS:
        path = root / name
        if not path.exists():
            continue
        for item in (load_yaml(path).get("enrichment") or []):
            item = item or {}
            for problem in cs.diagnose_table_text_description(item.get("table_text_description")):
                problems.append(f"[경고] {name} 공통 table_text_description: {problem}.")
    return problems


def check_table_format_pairs(root: Path) -> list[str]:
    """파서와 청커의 `output.table_format` 이 다르면 경고한다.

    custom_fields 레코드형 문서는 파서가 청크 본문을 완성해 넘기므로 그 표 모양은 파서 값을
    따르고, 일반 문서는 청커 값을 따른다. 두 값이 다르면 문서 종류에 따라 최종 청크의 표
    모양이 갈린다. 해석은 기동과 같은 규칙을 쓴다 — 파서는 키가 없으면 html 이고
    (`ParserCore._normalize_table_format`), 청커는 레거시 `export_to_html` 까지 본다.
    """
    problems: list[str] = []
    pairs = [(root / p, root / c) for p, c in TABLE_FORMAT_PAIRS]
    # 액티비티 폴더(activities/parse/ 또는 사이트의 그 폴더)면 청커는 옆의 chunk/ 폴더, 없으면 표준 청커 폴더
    if (root / "config.yaml").exists():
        chunker = root.parent / "chunk" / "config.yaml"
        if not chunker.exists():
            chunker = REPO_ROOT / "genon" / "preprocessor" / "activities" / "chunk" / "config.yaml"
        pairs.append((root / "config.yaml", chunker))
    for parser_path, chunker_path in pairs:
        parser_name, chunker_name = parser_path.name, chunker_path.name
        if not (parser_path.exists() and chunker_path.exists()):
            continue
        parser_out = load_yaml(parser_path).get("output") or {}
        chunker_out = load_yaml(chunker_path).get("output") or {}
        parser_fmt = cp.resolve_table_format_setting(
            {"table_format": parser_out.get("table_format", "html")})
        chunker_fmt = cp.resolve_table_format_setting(chunker_out)
        if parser_fmt != chunker_fmt:
            problems.append(
                f"[경고] {parser_name} 의 table_format({parser_fmt})과 {chunker_name} 의 "
                f"table_format({chunker_fmt})이 다릅니다. custom_fields 레코드형 문서의 표는 "
                f"파서 값, 일반 문서의 표는 청커 값으로 나갑니다. 같은 값으로 맞추세요."
            )
    return problems


def roots_of(target: Path | None) -> list[Path]:
    """검사할 설정 폴더들.
    인자 없음        표준 resource/ + 표준 파서 액티비티 폴더 전부(activities/parse*/ — custom_fields 는 파서 설정에만 있다)
    사이트 루트      그 resource/ + activities/parse*/ 전부(genon/sites/<site>/ 또는 NFS 의 사이트 사본)
    그 밖의 폴더     그 폴더 하나(종전과 같다 — resource/ 나 액티비티 폴더 하나)
    """
    def parser_folders(activities: Path) -> list[Path]:
        return sorted(p for p in activities.glob("parse*/") if (p / "config.yaml").is_file())

    preprocessor = REPO_ROOT / "genon" / "preprocessor"
    if target is None:
        return [preprocessor / "resource", *parser_folders(preprocessor / "activities")]
    if (target / "resource").is_dir() and (target / "activities").is_dir():
        return [target / "resource", *parser_folders(target / "activities")]
    return [target]


def main() -> int:
    ap = argparse.ArgumentParser(description="배포 전 custom_fields 설정 점검")
    ap.add_argument(
        "resource_dir", nargs="?", default=None,
        help="검사할 설정 디렉터리(프로세서 config 와 custom_field yaml 이 있는 곳) 또는 사이트 루트"
             "(resource/ 와 activities/ 가 있는 폴더). 없으면 저장소의 표준 resource/ 와 모든 액티비티 폴더",
    )
    args = ap.parse_args()

    target = Path(args.resource_dir).expanduser().resolve() if args.resource_dir else None
    if target is not None and not target.is_dir():
        print(f"[치명] 디렉터리가 없습니다: {target}")
        return 2
    code = 0
    for root in roots_of(target):
        code = max(code, check_root(root))
        print()
    return code


def check_root(root: Path) -> int:
    """설정 폴더 하나를 점검해 결과를 찍고 종료 코드(0 통과 · 1 기동실패 · 2 치명)를 돌려준다.

    액티비티 폴더(…/activities/<slug>/)면 그 완성본의 설정 폴더(옆의 resource/)를 GENOS_RESOURCE_DIR 로 두고
    본다 — config.yaml 의 모델 프리셋이 기동과 같은 파일(사이트 값)에서 풀리게."""
    import os

    print(f"검사 대상: {root}\n")
    sibling = root.parent.parent / "resource" if root.parent.name == "activities" else None
    saved = os.environ.get("GENOS_RESOURCE_DIR")
    if sibling is not None and sibling.is_dir():
        os.environ["GENOS_RESOURCE_DIR"] = str(sibling)
    try:
        return _check_root(root)
    finally:
        if saved is None:
            os.environ.pop("GENOS_RESOURCE_DIR", None)
        else:
            os.environ["GENOS_RESOURCE_DIR"] = saved


def _check_root(root: Path) -> int:
    blocks = registered_blocks(root)
    if not blocks:
        if not any((root / name).exists() for name in PROCESSOR_CONFIGS):
            print("[치명] 프로세서 설정이 없습니다 — 경로가 맞는지 확인하세요.")
            return 2
        # custom_fields 는 선택 기능이다 — 등록이 없어도 프리셋·표 형식 검사는 그대로 한다
        print("[정보] 등록된 custom_fields 가 없습니다.\n")

    problems: list[str] = []
    seen_files: set[str] = set()
    for source, block, presets in blocks:
        problems.extend(check_block(source, block, root, seen_files, presets))
    # 모델 프리셋은 설정 파일 단위로 본다(그 폴더의 규칙 파일 참조 포함).
    problems.extend(check_model_presets(root))
    problems.extend(check_table_text_blocks(root))
    problems.extend(check_table_format_pairs(root))

    # `doc_type:` 을 적지 않은 custom_field yaml 은 배포되지만 쓰이지 않는다. 등록 블록에서 옮길 때
    # 이 줄을 빠뜨린 파일이 여기서 드러난다.
    registered_files = {
        str(b.get("config_file")) for _source, b, _presets in blocks if b.get("config_file")
    }
    problems.extend(
        f"[경고] {p.name}: 최상위 doc_type 없음, 등록되지 않아 쓰이지 않음 (맨 위에 doc_type: <이름> 추가 필요)"
        for p in sorted(root.glob("custom_field_*.yaml")) if p.name not in registered_files
    )

    blocking = [p for p in problems if p.startswith("[기동실패]")]
    body = [p for p in problems if p.startswith("[본문변화]")]
    warn = [p for p in problems if p.startswith("[경고]")]
    info = [p for p in problems if p.startswith("[정보]")]

    for line in blocking:
        print(line)
    if blocking:
        print()
    for line in body:
        print(line)
    if body:
        print()
    for line in warn:
        print(line)
    if warn:
        print()
    for line in info:
        print(line)
    if info:
        print()

    print("=" * 70)
    print(f"등록 {len(blocks)}건 검사 | 기동실패 {len(blocking)}건 | 본문변화 {len(body)}건")
    if blocking:
        print()
        print("기동실패가 있으면 이 설정으로는 서비스가 뜨지 않습니다. 배포 전에 고치거나,")
        print(f"첫 릴리스에 한해 {cs.VALIDATION_POLICY_ENV}=warn 으로 두어 경고만 남기게 하세요.")
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
