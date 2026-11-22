# 모니모 전처리기 (파싱, 청킹)개발 매뉴얼

이 문서는 모니모 환경에 배포된 문서 전처리기에서 문서 유형(doc_type)을 추가하고, 파싱·청킹 설정과 코드를 고쳐 반영하는 방법을 설명합니다.
대상 독자는 전처리기 스튜디오 화면에서 설정 파일과 `processor.py`를 편집하는 모니모 현장 개발자입니다. Python·YAML 의 기본 사용 경험을 전제로 하며, 전처리기 내부 구조는 몰라도 됩니다.
처음 읽는다면 [0.2 doc_type 추가 작업 순서](#02-doc_type-추가-작업-순서)를 먼저 봅니다. 작업 순서와 각 단계에서 볼 절이 정리되어 있습니다.

## 목차

- [0. 시작하기](#0-시작하기)
  - [0.1 화면 구성](#01-화면-구성) · [0.2 doc_type 추가 작업 순서](#02-doc_type-추가-작업-순서)
- [1. 파싱 단계: doc_type 추가](#1-파싱-단계-doc_type-추가)
  - [1.1 입력 형태에 맞는 kind 선택](#11-입력-형태에-맞는-kind-선택) · [1.2 입력 형태별 예시](#12-입력-형태별-예시) · [1.3 custom_field yaml 작성](#13-custom_field-yaml-작성) · [1.4 자주 사용하는 설정](#14-자주-사용하는-설정)
  - [1.5 doc_type 등록](#15-doc_type-등록) · [1.6 Python 추출기](#16-python-추출기) · [1.7 processor.py 수정이 필요한 경우](#17-processorpy-수정이-필요한-경우) · [1.8 파싱 config.yaml 옵션](#18-파싱-configyaml-옵션)
- [2. 청킹 단계: 확인 사항](#2-청킹-단계-확인-사항)
  - [2.1 청킹 단계 수정이 필요한 경우](#21-청킹-단계-수정이-필요한-경우) · [2.2 doc_type별 검증 설정](#22-doc_type별-검증-설정) · [2.3 processor.py 수정이 필요한 경우](#23-processorpy-수정이-필요한-경우) · [2.4 청킹 config.yaml 옵션](#24-청킹-configyaml-옵션)
- [3. 문제 해결](#3-문제-해결)
- 부록: [A. custom_fields 설정 레퍼런스](#부록-a-custom_fields-설정-레퍼런스) · [B. processor.py 확장 지점](#부록-b-processorpy-확장-지점) · [C. 결과 형식과 오류](#부록-c-결과-형식과-오류) · [D. 용어집](#부록-d-용어집) · [E. 지원 요청](#부록-e-지원-요청)

---

## 0. 시작하기

### 0.1 화면 구성

전처리기 스튜디오는 파싱 단계(parse activity)에서 원본 파일을 읽어 필드를 뽑고, 청킹 단계(chunk activity)에서 검색용 청크(chunk)로 나뉜 뒤 임베딩, 적재됩니다.

```
원본 파일 ──파싱 단계(parse)──▶ 파싱 결과 JSON ──청킹 단계(chunk)──▶ chunk 목록 ──▶ embedding·적재
```

설정·코드 편집과 저장·push, activity 추가·복제·삭제, doc_type 추가, 단건 실행은 모두 전처리기 스튜디오에서 하며 화면 사용 방법은 전처리기 스튜디오 사용 설명서를 봅니다. 이 문서는 무엇을 어떻게 고치는지를 다룹니다. 이 문서의 "기동 실패"는 설정 오류 때문에 activity를 실행할 수 없는 상태를 말합니다.

단계마다 편집할 수 있는 항목은 세 가지입니다.


| 편집 항목             | 파싱 단계                                           | 청킹 단계                           | 하는 일                                     |
| ----------------- | ----------------------------------------------- | ------------------------------- | ---------------------------------------- |
| ① yaml 편집         | `activities/parse/custom_field_<doc_type>.yaml` | 없음(문서 유형별 yaml 을 두지 않습니다)       | 문서 유형별 필드 추출과 청크 본문 구성 규칙                |
| ② processor.py 편집 | `activities/parse/processor.py`                 | `activities/chunk/processor.py` | 입력 구조 변환, doc\_type 별 옵션, 값 변환기, 청크 수정   |
| ③ config.yaml 옵션  | `activities/parse/config.yaml`                  | `activities/chunk/config.yaml`  | 단계 공통 옵션과 doc\_type 등록(파싱), 청크 크기·검증(청킹) |


프롬프트 파일(`activities/parse/prompt_*.md`)도 파싱 단계 폴더에 있습니다. 화면의 옵션 설명(툴팁)은 config.yaml 의 주석이며, 이 문서의 옵션 표는 그 주석을 요약한 것입니다. 모니모 config.yaml 에는 모니모가 바꾸는 키만 값으로 적혀 있고, 나머지 키는 주석 처리된 설명으로만 남아 있습니다. 값을 적지 않은 키는 코드 기본값으로 동작하며, 바꿀 때는 주석을 풀고 값을 고칩니다.

### 0.2 doc_type 추가 작업 순서

새 문서 유형은 아래 순서로 추가합니다. 앞 단계로 해결되면 다음 단계로 넘어가지 않습니다.


| 단계  | 수정 대상                                                                                                | 이 단계에서 처리하는 것                                       | 다음 단계로 넘어가는 기준                                                         |
| --- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| 1   | `custom_field_<doc_type>.yaml` 작성 + 등록(규칙 파일의 `doc_type:` 줄 또는 `config.yaml` 등록 블록) | 컬럼·키 이름으로 값 매핑, 값 표기 통일, 날짜 변환, 본문 구성, LLM 으로 필드 생성 | 원하는 값이 컬럼·키·CSS selector로 바로 잡히지 않고 본문 속 규칙으로 찾아야 할 때                  |
| 1-1 | yaml 의 `python:` 블록(Python 추출기)                                                                      | 본문에서 정규식 등 규칙으로 값 추출(`kind: document` 전용)           | 입력 구조 자체를 바꿔야 하거나, doc\_type 별로 공통 옵션을 바꿔야 하거나, 기본 변환기에 없는 값 변환이 필요할 때 |
| 2   | `processor.py`(훅 메소드·`CONFIG_BY_DOC_TYPE`·값 변환기)                                                     | 입력 구조 변환, doc\_type 별 옵션, 사이트 전용 값 변환, 청크 수정        | 훅으로도 처리할 수 없을 때(새 입력 형식, 처리 순서 변경 등)                                   |
| 3   | 담당자 요청                                                                                               | 훅 추가 또는 전처리기 처리 코드(`processing/core/`) 수정           | —                                                                      |


`processing/core/` 아래 파일은 직접 고치지 않습니다. 릴리스 갱신 때 덮어써지므로 3단계는 담당자에게 요청합니다([부록 E](#부록-e-지원-요청)).

**파싱 단계 체크리스트**

- [ ] 입력 형태를 보고 `kind`를 정했습니다([1.1](#11-입력-형태에-맞는-kind-선택))
- [ ] 템플릿을 복사해 `custom_field_<doc_type>.yaml`을 만들고 `schema: v2`를 남겼습니다([1.3](#13-custom_field-yaml-작성))
- [ ] `alias`가 실제 원본의 컬럼·키 이름과 일치합니다
- [ ] 검색에 쓸 값을 `body`에 넣었습니다(메타데이터에만 있는 값은 embedding 에 들어가지 않습니다)
- [ ] doc_type을 등록했습니다(규칙 파일의 `doc_type:` 줄 또는 `config.yaml` 등록 블록, [1.5](#15-doc_type-등록))
- [ ] 규칙으로 찾을 값이 있으면 `python:` 블록을 추가했습니다([1.6](#16-python-추출기))

**청킹 단계 체크리스트**

- [ ] 파일 하나가 `BIZ_ID` 하나이고 여러 청크로 나뉘는 유형이면 `validation.by_doc_type`에 `fail_on_any: true`를 추가했습니다([2.2](#22-doc_type별-검증-설정))
- [ ] 청킹 호출에도 `params.doc_type`이 넘어오는지 담당자에게 확인했습니다([2.1](#21-청킹-단계-수정이-필요한-경우))
- [ ] 두 config.yaml 의 `output.table_format`이 같은 값입니다([2.4](#24-청킹-configyaml-옵션))

**결과 확인 체크리스트**

청크가 생성되었다는 사실만으로는 검증이 끝나지 않습니다. `alias`가 입력 표기와 어긋나면 값만 비고 오류는 나지 않습니다.

- [ ] `params`에 `{"error_policy": "strict"}`를 넣어 실행했습니다(기본 `lenient`는 보강 단계 오류를 경고만 남기고 건너뜁니다)
- [ ] 건수가 입력 건수에서 필터·필수값·빈 본문 제외·병합을 반영한 예상 건수와 같습니다
- [ ] 필드 값이 샘플의 기대값과 같고, 청크마다 필드가 실렸으며 `meta: false` 필드는 빠졌습니다
- [ ] 청크 본문에 필요한 값과 항목명이 있고, 로그에 `WARNING` 줄이 없습니다

오류 없이 값이 비는 경우는 [3장](#3-문제-해결)에 있습니다. 1·2단계에서 고친 파일은 다음 릴리스에도 유지되도록 담당자에게 전달합니다.

---

## 1. 파싱 단계: doc_type 추가

### 1.1 입력 형태에 맞는 kind 선택

`custom_field_<doc_type>.yaml`의 `source.kind`는 원본이 어떤 구조인지를 정합니다. 모니모의 입력은 아래 6가지 형태 중 하나입니다.


| 입력 형태                             | `kind`                             | 모니모 doc\_type                                   | 예시                                     |
| --------------------------------- | ---------------------------------- | ----------------------------------------------- | -------------------------------------- |
| 엑셀 한 행 = 한 건                      | `rows`                             | menu, term                                      | [예시 A](#예시-a-엑셀-행-term)                |
| JSON 배열의 요소 하나 = 한 건              | `records`                          | faq, cs\_slf, cs\_sss, cs\_hpp, monimo\_event   | [예시 B](#예시-b-json-레코드-배열-cs_slf)       |
| 구분자로 나뉜 텍스트 한 줄 = 한 건             | `records` + `source.pre.delimited` | cs\_ssf(`.dtms`, `|@|`), stock\_insight(`.txt`) | [예시 C](#예시-c-구분자-텍스트-cs_ssf)           |
| 대상 하나를 설명하는 중첩 JSON               | `sections`                         | product\_hpp                                    | [예시 D](#예시-d-중첩-json-product_hpp)      |
| 마크다운 문서 + front matter            | `document`                         | product\_slf, product\_ssf                      | [예시 E](#예시-e-마크다운-문서-product_slf)      |
| 값 위치를 CSS selector로 지정할 수 있는 HTML | `html`                             | monimo\_news(JSON 안의 HTML)                      | [예시 F](#예시-f-json-안의-html-monimo_news) |


`rows`·`records`는 기본적으로 한 건이 청크 하나가 되고, `sections`·`document`·`html`은 문서 하나가 여러 청크로 나뉘며 추출한 값이 모든 청크에 실립니다.

doc_type 의 역할은 다음과 같습니다.

- 파싱 요청의 `params.doc_type`과 같은 doc_type으로 등록된(규칙 파일의 `doc_type:` 줄 또는 등록 블록) `custom_field_*.yaml`이 적용됩니다.
- 파싱 등록과 청킹 검증 설정은 비교할 때 대소문자와 앞뒤 공백을 무시합니다(`"Term "`과 `term`은 같고 `terms`는 다릅니다). 청킹 `processor.py`의 `CONFIG_BY_DOC_TYPE`은 받은 문자열 그대로 비교하므로, 파싱·청킹 호출에는 모두 공백 없는 소문자 doc_type 을 씁니다.
- 등록되지 않은 doc_type 으로 요청하면 파싱이 실패합니다(모니모 설정 `defaults.unknown_doc_type: fail`).

### 1.2 입력 형태별 예시

아래 예시는 모니모 실제 설정에서 핵심만 남겨 줄인 것입니다. 실제 파일에는 필드와 옵션이 더 있습니다.

#### 예시 A. 엑셀 행 (term)

입력(엑셀 시트, 첫 행이 헤더):

```
ID       | 회사명 | 용어(국문)      | 정의·설명                       | 최종수정일
SLF_0001 | 생명   |  해지  환급금   | 보험계약을 중도에 해지할 때…   | 2026-06-01
```

```yaml
schema: v2
source:
  kind: rows
fields:
  BIZ_ID: {alias: [ID, 아이디], default: null}
  GROUP_C:
    alias: [회사명, 회사]
    values: {SLF: [삼성생명, 생명], HPP: [삼성카드, 카드]}
  TERM: {alias: [용어(국문), 용어]}
  TERM_NORM: {alias: [용어(국문), 용어], transform: normalize}
  DEFINITION: {alias: [정의·설명, 설명]}
  SRC_LAST_MOD_DT: {alias: [최종수정일], transform: date_int}
require:
  fields: [TERM, DEFINITION]
body:
  fields: [TERM, DEFINITION]
  labels: {TERM: 용어, DEFINITION: 설명}
```

결과: 행 하나가 청크 하나가 되고, 본문은 `용어: 해지  환급금` / `설명: 보험계약을 중도에…` 두 줄입니다. 메타데이터는 `TERM_NORM="해지 환급금"`, `GROUP_C=SLF`, `SRC_LAST_MOD_DT=20260601`, `BIZ_ID=SLF_0001`입니다.

#### 예시 B. JSON 레코드 배열 (cs_slf)

입력:

```json
{"faq_list": [{"faqId": "LIFE-CS-01", "category1": "보험",
               "question": "보험금 청구는 어떻게 하나요?", "answer": "1) 청구서를…"}]}
```

```yaml
schema: v2
source:
  kind: records
  records_at: faq_list
fields:
  BIZ_ID: {alias: [faqId]}
  GROUP_C: {const: SLF}
  CS_CTGR_L1: {alias: [category1]}
  CUSTOM_TITLE: {alias: [question], transform: to_text}
  CONTENT: {alias: [answer], transform: to_text}
  SRC_LAST_MOD_DT: {alias: [게시일자], default: null, transform: date_int}
require:
  fields: [CUSTOM_TITLE]
body:
  fields: [CS_CTGR_L1, CUSTOM_TITLE, CONTENT]
  labels: {CS_CTGR_L1: 문의유형, CUSTOM_TITLE: 제목, CONTENT: 내용}
  split: true
  repeat: [CS_CTGR_L1, CUSTOM_TITLE]
```

결과: 레코드 하나가 청크 하나가 되고, 본문은 `문의유형: 보험` / `제목: 보험금 청구는…` / `내용: 1) 청구서를…`입니다. 날짜 값이 없으면 `SRC_LAST_MOD_DT=0`입니다. 답변이 길면 여러 청크로 나뉘고, 나뉜 청크마다 문의유형·제목 줄이 반복됩니다.

#### 예시 C. 구분자 텍스트 (cs_ssf)

입력(`.dtms`, 한 줄이 한 건이며 `|@|`로 칸을 나눔):

```
자동차|@|담보|@||@|[보상콜] 휴대품과 소지품…|@|"<style>…<table>…"
```

```yaml
schema: v2
source:
  kind: records
  pre:
    delimited:
      separator: "|@|"
      columns: [대분류, 중분류, 소분류, 제목, 내용]
fields:
  BIZ_ID:
    template: "{{CS_CTGR_L1}}|{{CUSTOM_TITLE}}|{{CONTENT}}"
    transform: {name: hash, prefix: SSF_CS_, length: 16}
  GROUP_C: {const: SSF}
  CS_CTGR_L1: {alias: [대분류]}
  CUSTOM_TITLE: {alias: [제목], transform: to_text}
  CONTENT: {alias: [내용], transform: to_text}
require:
  fields: [GROUP_C]
body:
  fields: [CS_CTGR_L1, CUSTOM_TITLE, CONTENT]
  labels: {CS_CTGR_L1: 문의유형, CUSTOM_TITLE: 제목, CONTENT: 내용}
  split: true
  repeat: [CS_CTGR_L1, CUSTOM_TITLE]
```

결과: `BIZ_ID=SSF_CS_…`(16자리 hash)가 만들어지고, 내용 칸의 HTML 표는 `to_text`로 마크다운 표가 됩니다.

#### 예시 D. 중첩 JSON (product_hpp)

입력(파일 하나가 카드 상품 하나):

```json
{"wcmsId": "1202631", "code": "AAP1344", "cardTitle": "새마을금고 삼성카드 7",
 "benefit": ["새마을금고 현금카드 기능", …], "bubble": [{"title": "0.5%~3% 빅포인트 적립", …}], "htmlList": […]}
```

```yaml
schema: v2
source:
  kind: sections
  sections: {benefit: 주요 혜택, bubble: 혜택 상세, htmlList: 상품 문서}
  ignore_keys: [mpo, '*Img*', '*Lottie*', fontColor, bgColor]
fields:
  BIZ_ID: {alias: [wcmsId, id]}
  PRODUCT_C: {alias: [code, productCode]}
  PRODUCT_NM: {alias: [cardTitle, productName]}
  GROUP_C: {const: HPP}
require:
  fields: [PRODUCT_NM]
body:
  fields: [PRODUCT_C, PRODUCT_NM]
  labels: {PRODUCT_C: 상품코드, PRODUCT_NM: 상품명}
```

`mpo`는 다른 카드(추천 상품)의 정보이므로 `ignore_keys`로 제외합니다. 제외하지 않으면 추천 상품 정보도 이 상품의 `BIZ_ID`가 붙은 청크로 만들어집니다(위 샘플에서 8건이 10건으로 늘어납니다).

결과: 섹션마다 요소가 하나씩(위 샘플 기준 8건) 만들어지고, 각 본문은 `[혜택 상세] 0.5%~3% 빅포인트 적립` / `상품코드: AAP1344` / `상품명: 새마을금고 삼성카드 7` / 섹션 내용 순서입니다. `sections`에 적지 않은 나머지 키(예: `cardSlogan`)는 `개요` 섹션으로 모이고, 모든 요소에 `BIZ_ID=1202631`, `GROUP_C=HPP`가 실립니다. 실제 설정은 여기에 연회비(`FEE`)를 만드는 `llm` 블록을 더 둡니다.

#### 예시 E. 마크다운 문서 (product_slf)

입력:

```markdown
---
title: "삼성 s교통상해보험(2501)(무배당) 상품요약서"
created_at: "2026-01-12"
---
# 삼성 s교통상해보험(2501)(무배당) 상품요약서 …
```

```yaml
schema: v2
source:
  kind: document
  pre:
    markdown:
      front_matter: {exclude_text_fields: ['*'], on_missing: warn}
fields:
  BIZ_ID:
    alias: [$file]
    transform: {name: hash, prefix: SLF_PROD_, length: 16}
  PRODUCT_NM:
    alias: [title]
    transform: [{name: regex_sub, pattern: '\s*상품요약서$', repl: ''}]
  created_date: {alias: [created_at], transform: date_int}
  GROUP_C: {const: SLF}
body:
  once: [created_date]
  labels: {created_date: 출시일}
```

결과: 모든 청크(샘플 기준 7건)에 `PRODUCT_NM="삼성 s교통상해보험(2501)(무배당)"`, `created_date=20260112`, `BIZ_ID=SLF_PROD_…`(16자리 hash)가 실립니다. `출시일: 20260112` 줄은 첫 청크의 `HEADER:` 줄 바로 다음에만 들어가고, front matter 는 본문에서 빠집니다.

#### 예시 F. JSON 안의 HTML (monimo_news)

입력(파일명 `TD00008415_d_5199.html.json`, `content` 키에 HTML):

```
{"content": "<div class=\"newsletter-article-wrap\" newsletter-title=\"이슈산책\">…
             <p class=\"new-banner-headline\">계산대 없는 무인가게, …</p>…"}
```

```yaml
schema: v2
source:
  kind: html
  pre:
    json: {body_from: [content], format: auto, on_missing: skip}
fields:
  BIZ_ID:
    alias: [$file]
    transform: {name: regex_extract, pattern: '^(TD\d+)'}
  GROUP_C: {default: IFP}
  CUSTOM_TITLE: {select: .new-banner-headline}
  CATEGORY: {select: .newsletter-article-wrap, attr: newsletter-title}
  SUMMARY: {select: .article-summary-box}
body:
  once: [CATEGORY, CUSTOM_TITLE]
  labels: {CATEGORY: 카테고리, CUSTOM_TITLE: 제목}
```

결과: 샘플은 청크 2건이 되고, 첫 청크만 `카테고리: 이슈산책` / `제목: 계산대 없는 무인가게, 누가 열고 누가 찾을까요?`로 시작합니다(이 샘플에는 섹션 경로가 없습니다. 섹션 경로가 있으면 두 줄은 `HEADER:` 줄 바로 다음에 붙습니다). 모든 청크에 `BIZ_ID=TD00008415`, `CATEGORY=이슈산책`, `GROUP_C=IFP`가 실립니다.

### 1.3 custom_field yaml 작성

빈 파일에서 시작하지 말고 템플릿을 복사합니다. 템플릿에는 항목마다 `[필수]`/`[선택]` 표시와 설명, 흔한 실수가 주석으로 들어 있습니다.

전처리기 스튜디오 파싱 단계의 yaml 편집에서 `custom_field_<doc_type>.yaml` 파일을 새로 만들고, `kind`에 맞는 템플릿(`resource/templates/` 폴더) 내용을 붙여 넣은 뒤 [1.2](#12-입력-형태별-예시)의 예시처럼 쓰지 않는 항목을 지우고 실제 컬럼·키 이름으로 채웁니다.


| `kind`     | 템플릿                                   | 참고할 모니모 설정                                                                            |
| ---------- | ------------------------------------- | ------------------------------------------------------------------------------------- |
| `rows`     | `custom_field_TEMPLATE_rows.yaml`     | `custom_field_menu.yaml`, `custom_field_term.yaml`                                    |
| `records`  | `custom_field_TEMPLATE_records.yaml`  | `custom_field_faq.yaml`, `custom_field_monimo_event.yaml`, `custom_field_cs_ssf.yaml` |
| `sections` | `custom_field_TEMPLATE_sections.yaml` | `custom_field_product_hpp.yaml`                                                       |
| `document` | `custom_field_TEMPLATE_document.yaml` | `custom_field_product_slf.yaml`, `custom_field_product_ssf.yaml`                      |
| `html`     | `custom_field_TEMPLATE_html.yaml`     | `custom_field_monimo_news.yaml`                                                       |



파일 최상위에 `schema: v2` 한 줄이 반드시 있어야 합니다. 이 줄이 없으면 전처리기가 기동하지 않습니다. 지원하지 않는 키도 대부분 기동 실패로 처리하며, 경고만 남기는 예외는 [부록 A.1](#a1-설정-키와-지원-범위)에 있습니다.


| 블록        | 하는 일                                                                                    |
| --------- | --------------------------------------------------------------------------------------- |
| `source`  | 입력 구조(`kind`), 레코드 배열 위치(`records_at`), 섹션(`sections`·`ignore_keys`), 포맷 전처리(`pre`)     |
| `fields`  | 필드마다 값을 얻는 방법(`alias`·`select`·`const`·`default`)과 후처리(`values`·`transform`·`template`) |
| `require` | 이 필드가 비면 그 건을 건너뜁니다                                                                     |
| `body`    | 청크 본문 구성(`fields`·`labels`), 긴 본문 분할(`split`), 청크마다 반복할 값(`repeat`)·첫 청크에만 넣을 값(`once`) |
| `llm`     | 원본에 없는 필드를 LLM 으로 만듭니다(`out` 출력 필드, `in` 입력 필드)                                         |
| `python`  | Python 함수로 값을 추출합니다(`kind: document` 전용, [1.6](#16-python-추출기))                         |


`kind` 별로 쓸 수 있는 키와 변환기 목록은 [부록 A](#부록-a-custom_fields-설정-레퍼런스)에 있습니다.

### 1.4 자주 사용하는 설정

**1. 컬럼·키 이름이 원본마다 다를 때** — `alias`에 원본에서 쓰는 이름을 모두 적습니다.

```yaml
  DEFINITION: {alias: [정의·설명, 정의 설명, 설명, 정의]}
```

**2. 날짜를 `YYYYMMDD` 정수로** — `date_int`를 씁니다. "진행중"처럼 날짜로 변환할 수 없을 때 사용할 값은 `on_error`로 정합니다.

```yaml
  SRC_LAST_MOD_DT: {alias: [최종수정일], transform: date_int}       # "2026-06-01" -> 20260601
  VALID_TO: {alias: [종료일], transform: {name: date_int, on_error: 99991231}}
```

**3. 회사명·코드 표기 통일과 고정값** — `values`는 여러 표기를 표준 코드 하나로 모으고, `const`는 원본 값과 관계없이 고정값을 넣습니다.

```yaml
  GROUP_C:
    alias: [mnmFncoCd, 회사명]
    values: {IFP: [0, "00", 모니모], SLF: [2, "02", 삼성생명, 생명]}
  SALE_STATUS: {const: SALE}
```

**4. 원본에 ID 가 없을 때** — 여러 필드를 `template`으로 이어 `hash`를 만들거나(cs_ssf), 파일명(`$file`)에서 뽑습니다(cs_hpp, monimo_news).

```yaml
  BIZ_ID:
    template: "{{CS_CTGR_L1}}|{{CUSTOM_TITLE}}|{{CONTENT}}"
    transform: {name: hash, prefix: SSF_CS_, length: 16}
  # 파일명에서 뽑기: alias: [$file] + transform: {name: regex_extract, pattern: '^(TD\d+)'}
```

**5. 여러 필드를 본문으로 합치고 긴 본문 나누기** — `body.fields` 순서대로 `항목명: 값` 줄을 만들고, `split: true`면 긴 본문을 나누며 `repeat` 필드를 나뉜 청크마다 반복합니다.

```yaml
body:
  fields: [CS_CTGR_L1, CUSTOM_TITLE, CONTENT]
  labels: {CS_CTGR_L1: 문의유형, CUSTOM_TITLE: 제목, CONTENT: 내용}
  split: true
  repeat: [CS_CTGR_L1, CUSTOM_TITLE]
```

원본에 없는 필드를 LLM 으로 만들 때는 `llm` 블록을 씁니다(예: `custom_field_product_hpp.yaml`의 연회비 `FEE`). 작성법은 [부록 A](#부록-a-custom_fields-설정-레퍼런스)를 봅니다.

### 1.5 doc_type 등록

전처리기 스튜디오의 doc_type 추가를 쓰면 규칙 파일 최상위(`schema: v2` 줄 아래)에 `doc_type: <이름>` 줄이 적혀 등록되며, `config.yaml`은 고치지 않습니다. 이 방식에는 `enable`이 없습니다. 끄고 켤 수 있어야 하면 아래처럼 `activities/parse/config.yaml`의 `enrichment` 목록에 등록 블록을 둡니다.

```yaml
enrichment:
  # … 이미 있는 항목 …
  # 공지사항
  - custom_fields:
      enable: true                          # 이 doc_type 설정을 쓸지. true | false
      doc_type: notice                      # 요청의 doc_type 이 이 값과 같을 때 적용(대소문자 무시)
      config_file: custom_field_notice.yaml # 규칙 파일. 파일명만 적음(이 폴더 기준)
```

- 잠시 쓰지 않을 유형은 블록을 지우지 말고 `enable: false`로 끕니다. 끈 유형은 등록되지 않은 것과 같습니다.
- 모니모 설정은 `defaults.unknown_doc_type: fail` 이므로 등록되지 않았거나 꺼진 doc_type 으로 요청하면 파싱이 실패합니다. 유형을 끌 때는 그 doc_type 을 보내는 적재 workflow 설정 변경을 담당자에게 요청합니다.
- `doc_type`을 적지 않은 등록 블록은 모든 요청에 적용됩니다. 모니모 설정에는 이런 블록을 두지 않습니다.
- 같은 doc_type 을 등록 블록(꺼진 블록 포함)과 규칙 파일, 또는 두 규칙 파일에 함께 등록하면 activity 실행이 설정 오류로 실패합니다.
- 다른 doc_type을 복사해 추가한 규칙 파일은 원본과 같은 필드를 추출하므로 새 문서에 맞게 고칩니다([1.3](#13-custom_field-yaml-작성)).

### 1.6 Python 추출기

yaml 은 "어느 컬럼·키의 값을 어느 필드에 넣을지"를 적는 곳입니다. 본문 속 `계약번호: AB-123`처럼 규칙으로 찾아야 하는 값은 LLM 대신 짧은 Python 함수로 찾는 편이 빠르고 정확하며 호출 비용도 들지 않습니다.

만드는 것은 두 가지입니다.

1. Python 파일 — 본문 text 를 받아 `{필드: 값}` dict 를 돌려주는 함수
2. yaml 의 `python:` 블록 — 파일(`file`), 함수 이름(`callable`, 기본값 `extract`), 결과로 받을 필드(`out`)

```yaml
# activities/parse/custom_field_contract.yaml
schema: v2
source:
  kind: document
python:
  file: contract_extract.py      # 이 yaml 과 같은 폴더
  callable: extract
  out: [CONTRACT_NO, AMOUNT]
fields:
  AMOUNT: {transform: [to_int]}  # 반환값도 다른 필드처럼 transform 을 거침
```

```python
# activities/parse/contract_extract.py
import re

CONTRACT = re.compile(r"계약번호[:\s]*([A-Z0-9-]+)")
AMOUNT = re.compile(r"계약금액[:\s]*([0-9,]+)\s*원")


def extract(text, document=None, output_fields=None, **kwargs):
    contract = CONTRACT.search(text or "")
    amount = AMOUNT.search(text or "")
    return {
        "CONTRACT_NO": contract.group(1) if contract else None,
        "AMOUNT": amount.group(1) if amount else None,   # "1,250,000" -> to_int 가 1250000 으로 변환
    }
```

- `def extract(text)`처럼 `text` 하나만 받아도 됩니다. `kwargs`에는 요청 파라미터(doc_type 등)가 들어옵니다. 사내 API 를 조회하려면 `async def`로 작성합니다.
- `kind: document` 에서만 쓸 수 있고 `llm` 블록, 그리고 front matter 키나 파일명(`$file`)을 가리키는 `alias`와 함께 쓸 수 없습니다. 등록은 [1.5](#15-doc_type-등록)와 같습니다.
- 파일이 없거나 함수 이름이 틀리면 전처리기가 기동하지 않습니다.

사이트 전용 값 변환기는 [1.7](#17-processorpy-수정이-필요한-경우), LLM 응답을 직접 해석하는 파서는 [부록 B](#부록-b-processorpy-확장-지점)를 봅니다.

### 1.7 processor.py 수정이 필요한 경우

yaml 과 Python 추출기로 처리할 수 없을 때 파싱 단계의 `activities/parse/processor.py`를 고칩니다. 고치는 위치는 세 곳입니다.


| 상황                           | 고치는 위치                                                       | 예                                  |
| ---------------------------- | ------------------------------------------------------------ | ---------------------------------- |
| 원본 구조가 yaml 이 기대하는 구조와 다릅니다  | `edit_input(ext, doc_type, data, work_dir=None, **kwargs)` 훅 | 목록과 상세가 다른 키로 나뉜 JSON 을 레코드 배열로 합침 |
| 특정 doc\_type 에서만 공통 옵션을 바꿉니다 | `CONFIG_BY_DOC_TYPE`                                         | 표가 없는 유형만 표 설명 LLM 호출을 끔           |
| 기본 변환기에 없는 값 변환이 필요합니다       | 파일 최상위의 `tb.register_transform(...)`                         | `"1,200원"` → `1200`                |


```python
# activities/parse/processor.py
tb.register_transform("won_to_int",
                      lambda v: int(str(v).replace(",", "").replace("원", "")) if v not in (None, "") else v)

class DocumentProcessor(ParserCore):
    CONFIG_BY_DOC_TYPE = {
        "notice": {"table_text_desc": False},       # 이 유형만 텍스트 표 설명을 끔
    }
```

등록한 변환기는 yaml 에서 `transform: [won_to_int]`처럼 이름으로 부릅니다. `edit_input`은 `doc_type`으로 대상을 제한하고, 수정할 것이 없으면 받은 `data`를 그대로 반환합니다.

processor.py 로 할 수 없는 것도 있습니다. 새 입력 형식의 파서 추가, 처리 순서 변경, `processing/core/`의 동작 변경은 담당자에게 요청합니다([0.2](#02-doc_type-추가-작업-순서)의 3단계). 훅 메소드 전체 목록과 시그니처, 반환 규칙은 [부록 B](#부록-b-processorpy-확장-지점)에 있습니다.

### 1.8 파싱 config.yaml 옵션

`activities/parse/config.yaml`에 값이 적힌 옵션입니다. "바꿀 때"에 재적재로 표시한 옵션은 바꾸면 이미 적재한 문서를 다시 적재해야 결과가 맞춰집니다.


| 옵션                                                       | 하는 일                                      | 모니모 값           | 바꿀 때                                                                                  |
| -------------------------------------------------------- | ----------------------------------------- | --------------- | ------------------------------------------------------------------------------------- |
| `defaults.unknown_doc_type`                              | 등록되지 않은 doc\_type 요청을 어떻게 처리할지            | `fail`          | `warn`이면 경고만 남기고 일반 문서로 파싱합니다. 모니모는 `fail`을 유지합니다                                     |
| `defaults.log_level`                                     | 로그 상세도. `5`=DEBUG \~ `1`=CRITICAL, `0`=끄기 | `4`             | 문제를 조사할 때만 `5`로 올립니다                                                                  |
| `enrichment`의 `custom_fields`                            | doc\_type 하나에 등록 블록 하나                    | doc\_type 마다 1개 | 스튜디오의 doc\_type 추가는 규칙 파일의 `doc_type:` 줄로 등록하므로 이 목록은 고치지 않습니다([1.5](#15-doc_type-등록))   |
| `enrichment`의 `table_text_description.enable`            | 텍스트 표에 검색용 설명을 LLM 으로 만들지                 | `true`          | 끄면 표 설명이 청크에서 빠집니다. 재적재                                                               |
| `table_text_description.model_preset`                    | 표 설명에 쓸 모델 이름(`model_presets.yaml`의 키)    | `default`       | 모델 연결은 [부록 A.7](#a7-모델-서빙-연결-설정)을 봅니다                                                    |
| `table_text_description.model_context_tokens` · `max_tokens` | 모델의 입력 한도와 응답 길이 상한(토큰). 한 번에 담는 표 개수를 정합니다 | `40000` · `4000` | 모델이 바뀌면 그 모델의 한도에 맞춥니다. `max_tokens`는 서빙의 출력 상한 이하로 둡니다 |
| `table_text_description.prompt_template_file` | 표 설명 프롬프트 파일(이 폴더 기준) | `prompt_table_text_description_rag.md` | 비우면 표 설명을 건너뜁니다. 재적재 |
| `table_text_description.rag.retrieval_context_max_chars` | 표 설명 본문의 최대 글자 수                          | `200`           | 늘리면 설명이 길어지고 LLM 호출이 늘어납니다. 재적재                                                       |
| `table_text_description.rag.key_fact_limit`              | 표에서 뽑을 핵심 사실 개수                           | `2`             | 위와 같습니다. 재적재                                                                          |
| `table_text_description.rag.key_fact_max_chars` | 핵심 사실 1개의 최대 글자 수 | `120` | 위와 같습니다. 재적재 |
| `layout.layout_model_type`                               | 페이지 구조를 찾는 모델                             | `genos_layout`  | `docling_layout`은 서버 없이 동작하지만 품질이 다릅니다                                                |
| `layout.genos_layout.*` | layout 서버 호출 옵션(`model_preset`·`page_batch_size`·`timeout` 등) | `layout` · `128` · `3600` 등 | `page_batch_size`를 늘리면 빨라지지만 서버 부하가 커집니다. 페이지가 시간 초과로 구조만 받으면 `timeout`을 늘립니다 |
| `output.format`                                          | 파싱 결과 형식                                  | `docling`       | 청킹 단계 입력용이므로 바꾸지 않습니다                                                                 |
| `output.table_format`                                    | 레코드 단위 문서의 표를 글로 쓰는 형식                    | `markdown`      | 청킹 config.yaml 의 같은 키와 같은 값으로 둡니다. 바꾸면 표가 든 레코드의 hash `BIZ_ID`(예: cs\_ssf)가 바뀝니다. 재적재 |


- 표에 없는 옵션(`formats`, `ocr`, `pdf_output`, 그 밖의 `enrichment` 항목 등)은 config.yaml 에 주석으로만 있으며 코드 기본값으로 동작합니다. 바꿀 때는 그 주석을 풀고 값을 고칩니다.
- 일부 값은 요청마다 activity 인자의 `params`로 바꿀 수 있으며 config.yaml 보다 우선합니다(예: `{"table_text_desc": 0}`은 그 요청만 표 설명을 끔). 쓸 수 있는 키는 [부록 A.6](#a6-params와-activity-인자)에 있습니다.
- 프롬프트는 `activities/parse/prompt_*.md` 파일에 있고 config.yaml 의 `prompt_template_file`이 파일명으로 부릅니다. 적은 파일이 없거나 비어 있으면 기동이 실패합니다.

---

## 2. 청킹 단계: 확인 사항

### 2.1 청킹 단계 수정이 필요한 경우

대부분의 doc_type 은 청킹 단계를 수정하지 않아도 됩니다. 본문 구성(`body`)처럼 유형별 청크 동작은 파싱 단계의 custom_field yaml 에 적고, 그 결과가 청킹 단계로 넘어오기 때문입니다.


| 상황                                                       | 할 일                                              | 절                                 |
| -------------------------------------------------------- | ------------------------------------------------ | --------------------------------- |
| 공통 검증과 기본 청킹으로 충분하고, 유형별 차이를 custom\_field yaml 로 표현했습니다 | 수정하지 않습니다                                        | —                                 |
| 한 문서를 여러 청크로 나누는 유형이라 일부 청크만 빠지면 내용이 끊깁니다                | `validation.by_doc_type`에 `fail_on_any: true` 추가 | [2.2](#22-doc_type별-검증-설정)        |
| 청크를 유형별로 다르게 고쳐야 합니다(본문 교체, 일부 제외, 필드 추가)                | 청킹 `processor.py` 수정                             | [2.3](#23-processorpy-수정이-필요한-경우) |


청킹 단계는 doc_type 을 파싱 결과에서 가져오지 않고 청킹 호출의 `params.doc_type` 에서만 읽습니다. 따라서 `by_doc_type`과 청킹 `processor.py`의 `CONFIG_BY_DOC_TYPE`은 청킹 호출에도 doc_type 이 넘어올 때만 적용됩니다. 적재 workflow 가 청킹 호출에 doc_type 을 넘기는지는 담당자에게 확인합니다.

### 2.2 doc_type별 검증 설정

청킹 단계는 내용이 없거나, 너무 짧거나, 같은 말이 반복되거나, 문자가 깨진 청크를 검사합니다. 모니모 설정은 걸린 청크를 적재에서 뺍니다(`action: drop`). `by_doc_type`은 이 공통 값을 doc_type 별로 덮어씁니다. 모니모 실제 설정은 다음과 같습니다.

```yaml
# activities/chunk/config.yaml
chunking:
  validation:
    enable: true
    action: drop
    by_doc_type:
      product_slf: {fail_on_any: true}
      product_ssf: {fail_on_any: true}
      product_hpp: {fail_on_any: true}
      monimo_news: {fail_on_any: true}
```

- `fail_on_any: true`는 걸린 청크가 하나라도 있으면 그 문서 전체를 실패로 처리합니다. 파일 하나가 `BIZ_ID` 하나이고 여러 청크로 나뉘는 유형(상품설명서, 관심소식)에 넣습니다. 일부만 적재되어 내용이 끊기는 것을 막습니다.
- 목록에 없는 doc_type(menu·term·faq·cs\_*·monimo_event·stock_insight)은 공통 값을 쓰며, 걸린 청크만 빠집니다. 레코드 하나가 청크 하나인 유형은 이 동작이 맞습니다.
- `by_doc_type`에서 덮어쓸 수 있는 키: `action`, `fail_on_any`, `min_chars`, `row_min_chars`, `repeat_*`, `broken_*`, `table_min_chars`, `max_chars`.
- 검증 설정은 요청 `params`로 바꿀 수 없고, 값을 잘못 적으면 전처리기가 기동하지 않습니다.

### 2.3 processor.py 수정이 필요한 경우

청킹 단계의 `activities/chunk/processor.py`에서 고치는 자리는 두 가지입니다.


| 고치는 자리                               | 하는 일                                                                                             | 예                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ | --------------------------------------- |
| `CONFIG_BY_DOC_TYPE`                 | doc\_type 별로 청킹 옵션을 바꿉니다                                                                         | `{"faq": {"chunking.chunk_size": 500}}` |
| `edit_chunk(text, info, **kwargs)` 훅 | 청크마다 불립니다. 문자열을 반환하면 본문 교체, `None`이면 그대로, `tb.DROP`이면 제외합니다. `info["fields"]`에 넣은 값은 청크 필드로 실립니다 | 상담직원용 문구가 든 청크 제외                       |


모니모는 현재 청킹 `processor.py`를 고치지 않고 기본 파일을 쓰며, `CONFIG_BY_DOC_TYPE`도 비어 있습니다. `CONFIG_BY_DOC_TYPE`은 청킹 호출에도 doc_type 이 넘어올 때만 적용됩니다([2.1](#21-청킹-단계-수정이-필요한-경우)). `edit_chunk`는 doc_type 유무와 관계없이 호출되므로, 특정 유형만 고치려면 훅 안에서 doc_type 을 확인합니다. 다른 훅과 상세 규칙은 [부록 B](#부록-b-processorpy-확장-지점)를 봅니다.

### 2.4 청킹 config.yaml 옵션

`activities/chunk/config.yaml`의 주요 옵션입니다. "모니모 값"이 `기본값(…)`인 옵션은 config.yaml 에 값이 적혀 있지 않아 코드 기본값으로 동작합니다. "바꿀 때"에 재적재로 표시한 옵션은 청크 본문이나 경계가 바뀌므로 이미 적재한 문서를 다시 적재해야 합니다.


| 옵션                                | 하는 일                                                                                                                                             | 모니모 값                                       | 바꿀 때                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- | --------------------------------------------- |
| `chunking.chunk_size`             | 청크 하나의 최대 글자 수. `0`은 나누지 않음                                                                                                                      | `1500`                                      | 줄이면 청크가 짧아지고 개수가 늘어납니다. 재적재                   |
| `chunking.min_chunk_size`         | 문서 단위 유형(`document`·`html`·`sections`)의 청크 크기 하한. 양수 `chunk_size`가 이 값보다 작으면 이 값으로 올립니다. `0` 이하는 보정 안 함. 행·레코드 단위 유형(`rows`·`records`)에는 적용되지 않음 | 기본값(`1024`)                              | `chunk_size`를 1024보다 작게 하려면 이 값도 함께 낮춥니다. 재적재 |
| `chunking.tokenizer_type`         | 문서 단위 유형의 `chunk_size` 단위. `char`=글자 수, `huggingface`=토큰 수. 행·레코드 단위 유형은 항상 글자 수                                                                 | 기본값(`char`)                              | 바꾸면 같은 `chunk_size` 값의 의미가 달라집니다. 재적재         |
| `chunking.chunk_mode`             | `split_only`=문서 구조 단위 유지, `resize_all`=작은 섹션을 합쳐 크기를 맞춤                                                                                          | 기본값(`split_only`)                         | 재적재                                           |
| `chunking.table_as_chunk`         | 표를 본문과 섞지 않고 별도 청크로 만들지                                                                                                                          | `false`                                     | 재적재                                           |
| `chunking.include_chunk_header`   | 청크 맨 앞에 `HEADER: <섹션 경로>` 줄을 붙일지                                                                                                                 | 기본값(`true`)                               | 끄면 검색 때 섹션 문맥이 사라집니다. 재적재                     |
| `chunking.text_cleanup.mode`      | `safe`=깨진 한글·보이지 않는 문자·특수 공백 정리, `off`=정리 안 함                                                                                                    | `safe`                                      | 재적재                                           |
| `chunking.text_cleanup.rules`     | `safe` 일 때 추가로 적용할 정규식 규칙(`line` 줄 삭제, `find`/`replace` 치환, `chunk` 청크 삭제)                                                                       | 장식용 글머리표 삭제 1건                              | 규칙을 더하면 청크 본문이 바뀝니다. 재적재                      |
| `chunking.validation.enable`      | 이상 청크 검증을 할지                                                                                                                                     | `true`                                      | —                                             |
| `chunking.validation.action`      | `drop`=걸린 청크를 적재에서 뺌, `report`=기록만                                                                                                               | `drop`                                      | —                                             |
| `chunking.validation.fail_on_any` | 걸린 청크가 하나라도 있으면 문서 전체 실패                                                                                                                         | 기본값(`false`)                              | doc\_type 별로는 `by_doc_type`에 둡니다              |
| `chunking.validation.by_doc_type` | doc\_type 별로 검증 값을 덮어씀                                                                                                                           | 상품설명서 3종·monimo\_news 에 `fail_on_any: true` | [2.2](#22-doc_type별-검증-설정)                    |
| `chunking.validation.max_chars`   | 청크 글자 수 상한. 넘은 청크는 버리지 않고 기록만 함. `0`은 검사 안 함                                                                                                     | 기본값(`0`)                                  | embedding 모델 입력 한도보다 조금 낮게 둡니다                |
| `output.table_format`             | 청크 본문에 표를 넣는 형식(`html`·`markdown`·`auto`)                                                                                                        | `markdown`                                  | 파싱 config.yaml 의 같은 키와 같은 값으로 둡니다. 재적재        |
| `output.table_row_serialization`  | 병합 셀이 있는 표 뒤에 `컬럼=값 | 컬럼=값` 행 문장을 덧붙일지                                                                                                           | `true`                                      | 재적재                                           |


- `chunk_size`·`chunk_mode`·`table_as_chunk`·`include_chunk_header`는 요청 `params`로 온 값이 config.yaml 보다 우선합니다. `text_cleanup`의 정규식이 잘못되었거나 모르는 키가 있으면 요청 때가 아니라 기동 때 실패합니다.

---

## 3. 문제 해결

설정 파일에 지원하지 않는 키가 있으면 기동에 실패하고, 오타이면 가장 가까운 키 이름을 함께 보여 줍니다. 아래는 기동 검사가 잡지
못하거나 결과가 예상과 다른 경우입니다.


| 증상                                                                  | 원인과 조치                                                                                                                                  |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `doc_type=… 에 맞는 custom_fields 등록이 없습니다` (`PARSE_P002`)             | 등록이 없거나, `enable: false`이거나, doc\_type 문자열이 다릅니다. 기본 제공 설정은 `defaults.unknown_doc_type: fail`이라 재시도 없이 실패합니다. 메시지에 나온 설정 파일을 고칩니다       |
| `doc_type`을 지정하지 않았는데 custom\_fields가 동작함                           | 등록 블록에 `doc_type` 키가 없으면 모든 요청에 적용됩니다                                                                                                   |
| 필드 없이 `doc_type`만 붙거나 metadata가 비어 있음                               | `unknown_doc_type: warn`에서 일치하는 등록이 없어 doc\_type 설정 없이 일반 문서로 처리되었습니다                                                                   |
| 청킹의 doc\_type별 검증·설정이 적용되지 않음                                       | 청킹 호출에 `doc_type`이 없습니다. 스튜디오 단건 실행에서는 청킹 단계에도 doc_type이 지정되었는지 확인하고, 적재 workflow는 담당자에게 확인합니다([2.1](#21-청킹-단계-수정이-필요한-경우))                       |
| `… custom_fields config 없음: …`                                      | `config_file`은 파싱 `config.yaml`과 같은 폴더 기준입니다. 파일명만 적습니다                                                                                 |
| 특정 필드만 계속 `null`                                                    | `alias`·CSS selector가 입력 표기와 다르거나, `llm`의 `out` 이름과 프롬프트가 내놓는 JSON 키가 다릅니다. `rows`·`records`에서 `require`에 넣지 않은 필드는 경고 없이 `null`이 됩니다   |
| 엉뚱한 값이 실림                                                           | 같은 이름 key가 얕은 곳과 깊은 곳에 모두 있으면 얕은 쪽이 우선합니다([부록 A.4](#a4-별칭이-값을-찾는-범위))                                                                   |
| 레코드 일부가 경고 없이 빠짐                                                    | `records_at`은 이름이 맞는 첫 배열만 찾습니다. 여러 부모 아래 나뉜 배열은 `edit_input`에서 합칩니다([부록 B.4](#b4-훅-메소드))                                               |
| 부모 객체의 값이 모든 레코드에서 기본값                                              | `alias`는 레코드 안에서만 찾습니다. `edit_input`에서 부모 값을 레코드에 넣습니다                                                                                  |
| `body.fields`의 필드가 본문에서 빠짐                                          | `fields`와 `llm` 어디에서도 값을 만들지 않는 필드입니다. `llm`을 주석 처리하고 그 출력 필드를 남긴 경우가 가장 흔합니다                                                           |
| `values`에 없는 값이 그대로 실림                                              | `values`는 목록에 없는 값을 바꾸지 않고 경고만 남깁니다                                                                                                     |
| 보강 단계가 실패했는데 activity는 성공                                           | 기본 `error_policy: lenient`입니다. 검증은 `strict`로 실행합니다([부록 A.6](#a6-params와-activity-인자))                                                                    |
| 모든 레코드가 제외됨                                                         | `skipped N/N records (missing required)` 경고를 확인합니다. 입력 표기가 `alias`와 달라 `require` 필드가 `null`이 되었습니다                                      |
| `필수 Excel 컬럼 매핑 실패`                                                 | rows의 `require` 필드와 일치하는 컬럼이 없습니다. 메시지의 `available` 목록과 `alias`를 대조합니다. 값만 빈 행은 제외만 됩니다                                                 |
| sections가 0건으로 성공                                                   | `source.on_missing: skip`이면 필수값이 없을 때 경고 후 0건을 반환합니다(기본 `error`는 실패)                                                                    |
| 본문이 빈 레코드가 빠짐                                                       | 정상입니다. 빈 vector 적재를 막기 위해 경고와 함께 제외합니다                                                                                                  |
| 청크 수가 예상보다 적음                                                       | 청크 검증(`action: drop`)에서 제외되었습니다. 결과 요약의 `chunk_validation`과 로그의 `[chunk_validation]`을 확인합니다([2.2](#22-doc_type별-검증-설정))                 |
| 청크가 1개만 나오거나 합쳐지지 않음                                                | `chunk_size: 0`은 병합·분할을 끄는 값입니다. 충분히 큰 양수를 쓰고, 필요하면 `chunk_mode: resize_all`을 지정합니다                                                     |
| xlsx가 행별로 나뉘지 않음, `doc_type`도 붙지 않음                                 | 일치하는 매핑이 없어 일반 표로 처리되었습니다. 등록과 `alias`를 확인합니다                                                                                           |
| `등록되지 않은 transforms 변환기: …` · `… 에 쓸 수 없는 인자입니다: …`                 | 기본 제공 10종([부록 A.2](#a2-transform-10종))과 `tb.register_transform`으로 등록한 것만 씁니다([부록 B.5](#b5-값-변환기와-llm-응답-파서)). 인자는 메시지의 `쓸 수 있는 인자`와 대조합니다 |
| `… 의 DocumentProcessor 는 ParserCore 를 상속해야 합니다` (청킹은 `ChunkerCore`) | `processor.py`의 클래스 이름이나 부모 클래스를 바꿨습니다. 되돌립니다                                                                                           |
| `파서 결과에 document/elements 가 없습니다`                                   | 파싱 `edit_output`이 `document` 또는 `elements`를 지웠습니다                                                                                       |
| 파싱 결과가 Docling 문서가 아니라 `elements`임                                  | `elements` 목록으로 반환되는 정상 결과일 수 있습니다. 적용된 매핑과 `output.format`을 확인합니다([부록 C.1](#c1-파싱-결과-형식))                                              |
| 모델 연결 오류로 실패                                                        | 모델 서빙 주소나 키가 실행 환경과 맞지 않습니다([부록 A.7](#a7-모델-서빙-연결-설정))                                                                                     |


---

## 부록 A. custom_fields 설정 레퍼런스

custom_field yaml의 키별 지원 범위입니다. 작성 방법은 [1.3](#13-custom_field-yaml-작성)과
[1.4](#14-자주-사용하는-설정)에, 세부 옵션은 `resource/templates/custom_field_TEMPLATE_*.yaml` 주석에 있습니다.
✔ = 지원, ✗ = 적으면 기동 실패, ⚠ = 기동은 되지만 무시되거나 일부만 동작합니다.

### A.1 설정 키와 지원 범위


| 기능                                                  | 설정 키                                                                               | rows      | records   | sections | document                      | html         |
| --------------------------------------------------- | ---------------------------------------------------------------------------------- | :---------: | :---------: | :--------: | :-----------------------------: | :------------: |
| 별칭                                                  | `alias`                                                                            | ✔         | ✔         | ✔        | ✔³                            | ✗ (`select`) |
| 파일명에서 가져오기                                          | `alias: [$file]`                                                                   | ✗         | ✔         | ✗        | ✔³                            | ✔            |
| 반복 key 전부 수집                                        | `collect`                                                                          | ✗         | ✔         | ✗        | ✗                             | ✗            |
| 상수 · 기본값 · 값 표기 통일 · 값 변환 · 필드 결합 · JSON 묶기 · 메타 제외 | `const` · `default` · `values` · `transform` · `template` · `pack` · `meta: false` | ✔         | ✔         | ✔        | ✔                             | ✔            |
| 객체를 값으로 받기                                          | `raw`                                                                              | ✗         | ✔         | ✔ 루트만    | ✗                             | ✗            |
| 순번 매기기                                              | `seq`                                                                              | ✔         | ✔         | ✗        | ✗                             | ✗            |
| 본문 구성 필드                                            | `body.fields`                                                                      | ✔ 선택      | ✔ 필수      | ⚠¹       | ✗                             | ✗            |
| 항목명                                                 | `body.labels`                                                                      | ✔         | ✔         | ✔        | ✔                             | ✔            |
| 긴 본문 분할                                             | `body.split`                                                                       | ✔         | ✔         | ✗²       | ✗                             | ✗            |
| 모든 청크에 반복 접두                                        | `body.repeat`                                                                      | ✔ split 시 | ✔ split 시 | ✗²       | ✔                             | ✔            |
| 첫 청크에만 1회                                           | `body.once`                                                                        | ✗         | ✗         | ✔        | ✔                             | ✔            |
| 본문을 메타 필드에 복사 · 짧은 청크 병합                            | `body.mirror_to` · `body.merge_short`                                              | ✗         | ✗         | ✗        | ✔                             | ✔            |
| 레코드 배열 위치                                           | `source.records_at`                                                                | ✗         | ✔         | ✗        | ✗                             | ✗            |
| 찾지 못할 때 정책                                          | `source.on_missing`                                                                | ✗         | ✔         | ✔        | ✗                             | ✗            |
| 여러 건 합치기                                            | `source.merge_rows`                                                                | ✔         | ✔         | ✗        | ✗                             | ✗            |
| 처리 대상 시트                                            | `source.sheets`                                                                    | ✔         | ✗         | ✗        | ✗                             | ✗            |
| 섹션 표시 이름 · 서브트리 제외                                  | `source.sections` · `source.ignore_keys`                                           | ✗         | ✗         | ✔        | ✗                             | ✗            |
| 형식 전처리                                              | `source.pre.markdown` / `.html`                                                    | ⚠ 무시      | ⚠ 무시      | ⚠ 무시     | ✔                             | ⚠ `.html`만   |
| 도형 마커 줄을 제목으로 변환 · JSON 안 본문 꺼내기                    | `source.pre.marker_headings` · `source.pre.json`                                   | ⚠ 무시      | ⚠ 무시      | ⚠ 무시     | ✔                             | ✔            |
| 구분자 텍스트 원천                                          | `source.pre.delimited`                                                             | ⚠ 무시      | ✔         | ⚠ 무시     | ⚠ 무시                          | ⚠ 무시         |
| 필수값(빈 값 제외)                                         | `require.fields`                                                                   | ✔ 건별      | ✔ 건별      | ✔ 문서 전체  | ✗                             | ✗            |
| 값 기반 제외                                             | `filter`                                                                           | ✔         | ✔         | ✗        | ✗                             | ✗            |
| 필드별 LLM 생성                                          | `llm:`                                                                             | ✔ 행별      | ✔ 레코드별    | ✔ 문서 1회  | ✔ 문서 1회(Python 추출기와 함께 사용 불가) | ✗            |
| doc\_type별 표 설명 덮어쓰기                                | `table_text_description`                                                           | ✔         | ✔         | ✔        | ✔                             | ✔            |


¹ sections의 `body.fields`는 공통 필드를 청크 접두에 실을지 정하는 스위치이며, 본문은 트리 순회로 만들어집니다.
² sections는 긴 본문을 항상 분할하고 접두도 자동으로 만들므로 이 키를 적으면 기동에 실패합니다.
³ document에서 `python:` 블록([1.6](#16-python-추출기))을 둔 설정에는 `alias`·`alias: [$file]`을 함께 쓸 수 없습니다(기동 실패). Python 추출기를 쓰지 않는 document 설정에서만 지원합니다.

- rows·records의 `body.fields`·`body.repeat` 값이 JSON·HTML이면 본문에는 평문으로 실립니다. 청크 메타(적재 컬럼)에도 평문이 필요하면 `transform: to_text`를 지정합니다.
- HTML 필드는 `select: ".title"`처럼 CSS selector를 지정하고, 속성값은 `attr: href`를 함께 씁니다. JSON 안에 HTML이 있으면 `source.pre.json`이 필요합니다.
- `meta: false`인데 어디에도 쓰이지 않는 필드는 경고만 남깁니다. `table_text_description` 블록의 오기입도 경고만 남깁니다.
- `extractor` 키는 적지 않습니다. `source.kind`가 정하며, 적은 값이 어긋나면 원인을 찾기 어려운 기동 실패가 납니다.
- `enrichment.toc.doc_type`(`normal` / `law`)은 목차 추출 방식 옵션이며 custom_fields의 doc_type과 무관합니다.

**기동 실패 로그를 읽을 때.** 오류 메시지에는 설정 키 대신 다음 내부 이름이 나옵니다.


| 설정 키                                                       | 오류 메시지의 이름                                                                                                 |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `alias`                                                    | rows `column_map` · records `key_map` · sections `shared_fields` · document `front_matter_map`             |
| `require.fields` · `llm`                                   | `required`(sections는 `required_shared_fields`) · `llm_fields`(document는 `output_fields`·`system_prompt` 등) |
| `template` · `default` · `const` · `values` · `transform`  | `derive` · `defaults` · `constants` · `value_map` · `transforms`                                           |
| `body.fields` · `labels` · `repeat` · `once` · `mirror_to` | `text_fields` · `field_labels` · `chunk_prefix_fields` · `first_chunk_fields` · `body_fields`              |
| `collect` · `raw` · `seq` · `meta: false`                  | `collect_key_map` · `raw_fields` · `sequence` · `meta_include`                                             |
| `source.records_at` · `on_missing` · `merge_rows`          | `records` · `missing_policy` · `row_merge`                                                                 |


### A.2 transform 10종

여러 개를 이어 붙일 수 있으며, 인자가 있으면 `{name: ...}` 형태로 적습니다. 잘못된 이름·인자·정규식은 기동할 때 실패합니다.


| 이름              | 인자                                                 | 동작                                                                          |
| --------------- | -------------------------------------------------- | --------------------------------------------------------------------------- |
| `date_int`      | `on_error` 기본 `0`                                  | 날짜 텍스트를 `YYYYMMDD` 정수로 바꿉니다. `26.07.01`·`20260713`·`260701`도 받습니다. 빈 값은 `0` |
| `normalize`     | —                                                  | NFKC, 양끝 공백 제거, 연속 공백 축약, casefold(중복 판정용)                                  |
| `regex_sub`     | `pattern` 필수, `repl` 기본 `""`                       | 정규식 치환(`"18,000원"` → `"18000"`)                                             |
| `regex_extract` | `pattern` 필수, `group` 기본 `1`, `on_error` 기본 `null` | 정규식 추출. 캡처 그룹이 없으면 `group: 0`                                               |
| `hash`          | `length` 기본 `16`, `prefix` 기본 `""`                 | SHA-1 16진 코드                                                                |
| `to_int`        | `on_error` 기본 `null`                               | 정수로 변환. 쉼표·단위는 무시하고, 소수(`1.5`)나 숫자가 둘 이상(`3~5개`)이면 `on_error`               |
| `percent`       | —                                                  | `"분자/분모"`를 백분율 정수(내림)로 바꿉니다(`"10600/25000"` → `42`). `template`으로 결합한 값에 겁니다. 분모가 0이면 `null` |
| `truncate`      | `length` 필수, `suffix` 기본 `""`                      | 길이 자르기(적재 컬럼 길이 맞춤)                                                         |
| `to_text`       | —                                                  | JSON/HTML/평문을 자동 판별해 평문으로 바꿉니다                                              |
| `to_json`       | `on_scalar`(`wrap`/`drop`), `key` 기본 `value`       | 유효한 JSON 문자열로 맞춥니다. 체인 맨 뒤에 두며 `body.*`·`pack`과 함께 쓸 수 없습니다                 |


`on_error`는 값이 있는데 변환하지 못했을 때 남길 값이며 빈 값에는 적용되지 않습니다.

```yaml
fields:
  FEE_AMT:
    alias: [수수료]
    transform:
      - {name: regex_sub, pattern: "[^0-9]", repl: ""}
      - {name: to_int}
```

### A.3 source 보조 키


| 키                     | 동작                                                                                                        |
| --------------------- | --------------------------------------------------------------------------------------------------------- |
| `records_at`          | 레코드 배열의 key 이름(임의 깊이에서 찾음). 생략하면 입력 배열의 원소마다 1건, 객체이면 그 안의 dict 배열을 찾고, 여러 개면 `alias`가 더 많이 맞는 배열을 씁니다    |
| `on_missing`          | records는 배열을 찾지 못했을 때, sections는 공통 필수값이 없을 때의 정책. `error`(기본) / `skip`(경고 후 0건)                          |
| `merge_rows`          | `group_by` 값이 같은 건을 한 건으로 합칩니다(`order_by`, `concat`, `separator`). 값 변환보다 먼저 실행됩니다                        |
| `ignore_keys`         | `kind: sections`에서 제외할 key 이름 glob(경로가 아님)                                                                |
| `pre.marker_headings` | `◈ 기본내용`처럼 도형 마커로만 계층을 나타낸 줄을 제목으로 바꿉니다                                                                   |
| `pre.json`            | JSON 입력에서 본문을 꺼낼 key 이름(`body_from`)과 형식(`format`)                                                        |
| `pre.delimited`       | 구분자 텍스트를 레코드로 읽습니다(`separator`·`columns` 필수). 텍스트 파일이면 확장자와 관계없이 먼저 처리합니다. 모니모 `cs_ssf`(`.dtms`)가 이 방식입니다 |


값으로 거르는 `filter`는 별도 블록이며 연산자는 `in`과 `not_in`입니다(예: `- {field: DEL_YN, not_in: [Y]}`).

### A.4 별칭이 값을 찾는 범위

`alias`는 key 이름으로 찾으며 경로로는 찾지 않습니다. `a.b.c`처럼 적어도 경로로 해석되지 않습니다.


| 대상                          | 탐색 범위                           | 우선순위                                   |
| --------------------------- | ------------------------------- | -------------------------------------- |
| records `source.records_at` | 문서 임의 깊이                        | 처음 찾은 1개                               |
| records `alias` · `collect` | 레코드 안 임의 깊이                     | 얕은 깊이부터, 같은 깊이에서는 선언 순서(`collect`는 전부) |
| sections `alias`            | 문서 루트의 스칼라만                     | 루트에서 한 번 확정                            |
| sections 본문                 | 트리 전체 자동 순회(깊이 ≤ 12, 노드 ≤ 5000) | 설정하지 않은 key도 포함                        |
| rows `alias`                | 시트 첫 행 헤더                       | 선언 순서                                  |
| document `alias`            | front matter 최상위 키만             | 선언 순서                                  |


records·sections에서 객체(`{…}`)는 값이 아니라 더 탐색할 구조로 취급하므로 `alias`만으로는 `null`이 됩니다.
객체를 통째로 적재 컬럼에 담으려면 그 필드에 `raw: true`와 `transform: [{name: to_json}]`을 함께 지정합니다.

### A.5 필드 조합과 LLM 설정

```yaml
fields:
  SUMMARY: {template: '{{QUESTION}} / {{ANSWER}}'}           # 만들어진 필드를 조합
  ROW_NO: {seq: {prefix: 'FAQ-', width: 4, start: 1}}        # FAQ-0001, FAQ-0002 …
  EXTRA: {pack: [QUESTION, ANSWER, ROW_NO]}                  # JSON 컬럼 하나로 묶기
llm:
  - out: [DETAIL_SUMMARY]                                    # 프롬프트가 반환하는 JSON 키와 같아야 함
    in: [DETAIL]                                             # LLM 입력으로 합칠 필드
    endpoint: {model_preset: default}
    parser: {type: json}                                     # 직접 구현하면 python(부록 B.5)
    params: {temperature: 0.0, max_tokens: 1000, timeout: 60}
    prompt:
      system: '입력을 한 문장으로 요약하여 DETAIL_SUMMARY 키를 가진 JSON 객체로 반환하세요.'
      user: |
        {{raw_text}}
```

`seq`는 재처리 시 순서가 달라질 수 있으므로 영구 식별자로 쓰지 않습니다. `pack`은 LLM 생성 필드와 순번이
확정된 뒤 실행됩니다. `rows`·`records`에서 LLM으로 만든 값을 본문에 넣으려면 `body.fields`에 추가합니다. `document`에서는 `body.repeat`·`body.once`를 사용합니다.

`kind: document`에서는 문서 하나에 LLM을 한 번 호출합니다. `in`을 지정하지 않고 `prompt.user`의 `{{raw_text}}`로
문서 본문을 전달합니다. `endpoint`·`parser`·`params`는 위 예시와 같습니다.

```yaml
schema: v2
source: {kind: document}
fields:
  TITLE: {default: null}
body:
  repeat: [TITLE]
  labels: {TITLE: 문서 제목}
llm:
  - out: [TITLE]
    endpoint: {model_preset: default}
    parser: {type: json}
    params: {temperature: 0.0, max_tokens: 1000, timeout: 60}
    prompt:
      system: '문서 제목을 TITLE 키의 JSON 객체로 반환하세요. 제목이 없으면 null을 반환하세요.'
      user: |
        다음 문서에서 제목을 추출하세요.
        {{raw_text}}
```

### A.6 params와 activity 인자

activity 인자는 pipeline 워커가 만들어 보냅니다. 오류 메시지와 결과를 읽을 때 필요합니다.

| activity | 인자(dict 하나) |
|---|---|
| parse · `parse_…` | `read_ref`(원본 위치) · `output_ref`(결과 위치) · `source_name`(선택) · `params`(선택) |
| chunk · `chunk_…` | `parsed_ref`(파싱 결과 위치) · `output_ref`(결과 위치) · `source_name`(선택) · `params`(선택) |

파싱과 청킹은 별도 호출이므로 `params.doc_type`도 각각 실려야 합니다. 적재 workflow가 청킹 호출에 `doc_type`을 넘기는지는 담당자에게 확인합니다.

`params`는 config.yaml보다 우선하며 그 호출에만 적용됩니다.

| activity | 자주 쓰는 `params` 키 |
|---|---|
| parse | `doc_type`, `toc`, `img_desc`, `chart_desc`, `table_desc`, `table_refine`, `table_text_desc`, `ocr_mode`, `doc_summary`, `save_images`, `use_hwp_sdk` |
| chunk | `doc_type`, `chunk_size`, `chunk_mode`, `include_chunk_header`, `chunk_overlap`, `table_as_chunk`, `export_to_html`, `table_format`, `compact_tables`, `table_row_serialization`, `text_cleanup`, `short_chunk_size` |
| 공통 | `llm_cache`, `workflow_id`(pipeline 워커가 넣습니다), `error_policy`, `request_deadline` — 동작 조건은 아래 표 |

- 0/1 플래그 형태의 키는 `0`/`1`과 `true`/`false`를 모두 받습니다.
- 로그 수준은 config.yaml의 `defaults.log_level`로만 정합니다. `params`의 `log_level`은 반영되지 않습니다.
- `table_desc`는 이미지 표 설명, `table_text_desc`는 텍스트 표 설명의 스위치입니다. 모니모 설정에서 켜져 있는 것은 텍스트 표 설명이므로, 호출별로 표 설명 LLM 호출을 끄려면 `table_text_desc: 0`을 사용합니다.

다음 세 키는 동작 조건이 따로 있습니다.


| 키                  | 값                    | 동작                                                                                                                                                               |
| ------------------ | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `error_policy`     | `strict` / `lenient` | 기본 `lenient`. 보강 단계 예외를 `strict`는 실패로, `lenient`는 경고 후 계속 처리합니다. 훅 예외와 파싱 실패에는 적용되지 않으며, 표 설명의 실행 중 실패는 `strict`에서도 건너뜁니다                                        |
| `request_deadline` | 양수 초                 | 워커와 단건 실행의 처리 시간 제한. 넘기면 `type: timeout`으로 실패합니다(재시도 대상)                                                                                                         |
| `llm_cache`        | `0` / `1`            | 파싱 단계의 LLM 응답 캐시. 실행 환경에 캐시 저장소가 설정되어 있고 `params.workflow_id`가 함께 전달될 때만 동작하며, 아니면 경고 없이 캐시를 쓰지 않습니다. 사용 가능 여부는 담당자에게 확인합니다 |


### A.7 모델 서빙 연결 설정

activity 설정은 모델 접속 정보를 `model_preset: <이름>`으로 참조합니다. preset은 다음 세 층을 키 단위로 합쳐 만들며 뒤의 층이 우선합니다.

| 순서 | 층 | 내용 |
|---|---|---|
| 1 | `resource/model_presets.yaml` | 표준 preset. 주소·키는 자리표시 값입니다 |
| 2 | `activities/<이름>/config.yaml`의 `model_presets` | 그 activity만의 조정(예: 시간 제한) |
| 3 | 실행 환경의 모델 접속 파일 | 모델 접속 실제 값. 담당자가 넣으며 바꿀 키만 적혀 있습니다 |

실제 접속 값은 담당자가 실행 환경에 넣으며, 바꿀 때는 담당자에게 요청합니다. 적용되면 `[model_preset] GENOS_MODEL_PRESETS_FILE 의 모델 preset 적용: <경로>` 로그가 남습니다.

| 용도 | preset 이름 |
|---|---|
| 문서 레이아웃 분석 | `layout` (`endpoint`, `api_key`) |
| 목차·메타데이터·문서 요약·텍스트 표 설명 | `default` |
| 이미지 설명·이미지 표 설명 / PPT 페이지 설명 | `image` / `page` |
| OCR | `ocr` (`ocr_endpoint`. 서빙 ID가 아니라 주소) |
| 음성 인식 / 민감정보 분류 | `whisper` (`url`) / `guardrail` (`url`, `workflow_id`, `api_key`) |

- 자리표시 값이 남으면 `모델 preset N개(…) 접속 정보가 비어 있음` 경고가 남고 처리는 계속됩니다. 경고에 나온 preset이 모두 사용하지 않는 기능용인지 확인합니다. 없는 preset 이름을 부르면 처리기 준비가 실패합니다.
- 사용하지 않는 기능은 끕니다. OCR은 기본이 `disable`(config.yaml 에 값 없음)이며 필요한 문서만 `params`의 `ocr_mode: "auto"`나 doc_type별 설정으로 켭니다. enrichment는 각 항목의 `enable: false`로 끕니다. PPT 페이지 설명(`formats.ppt.page_description`)은 기본으로 꺼져 있습니다.
- API 키는 비밀번호처럼 취급하고 문서·채팅·저장소에 쓰지 않습니다. 실제 값은 `resource/`나 activity 폴더에 쓰지 않습니다.

---

## 부록 B. processor.py 확장 지점

### B.1 수정 방법 선택

아래 순서대로 검토합니다. 앞 단계로 처리할 수 있는 작업을 코드로 구현하면 릴리스마다 다시 반영해야 합니다.
단계별 진행 기준은 [0.2](#02-doc_type-추가-작업-순서)에 있습니다.


| 순서  | 수단                                     | 적용 범위                    |
| --- | -------------------------------------- | ------------------------ |
| ①   | activity 인자 `params`                   | 그 호출                     |
| ②   | activity `config.yaml`                 | 모든 문서 공통 동작              |
| ③   | `custom_field_*.yaml`(`python:` 블록 포함) | 그 doc\_type의 값 추출과 청크 본문 |
| ④   | `processor.py`                         | 설정으로 표현할 수 없는 처리         |
| ⑤   | 담당자 요청                                 | 앞의 방법으로 처리할 수 없는 경우      |


④까지가 고객 개발자의 수정 범위입니다. `genon/preprocessor/processing/` 아래 처리 코드는 직접 고치지 않고
담당자에게 훅 추가를 요청합니다.

### B.2 수정 대상 파일


| 파일                              | 구성                                                                                                               |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `activities/parse/processor.py` | 상단 주석(처리 흐름 요약) → `ROUTES` → `CONFIG_BY_DOC_TYPE` → `config_by_condition` → 훅 3종                                 |
| `activities/chunk/processor.py` | `GenOSVectorMeta` → `GenosSmartChunker` → `ROW_CATEGORIES` → `CONFIG_BY_DOC_TYPE` → `config_by_condition` → 훅 3종 |


```
파싱   요청 -> 확장자 판정 -> doc_type별 설정 -> ROUTES -> 입력 읽기/변환[edit_input] -> 파싱
            -> 문서 경로: [edit_document] -> enrichment -> [edit_output] -> 응답
            -> 행·레코드 경로: 매핑/선택적 보강 -> [edit_output] -> 응답
청킹   파싱 결과 -> 형태 판별 -> doc_type별 설정 -> [edit_input] -> 분할 -> [edit_chunk]
            -> vector_meta 조립 -> [edit_output] -> 응답
```

`_`로 시작하는 메소드(`_start_job`, `_call_*`)는 훅 호출과 설정 적용 순서를 담당하므로 오버라이드하지 않습니다.
새 확장자는 대부분 `edit_input`에서 기존 형식(JSON·CSV 등)으로 변환해 처리하며, 이때 `ROUTES` 맨 앞에 그
확장자를 등록하고 `ext` 조건으로 변환 대상을 제한합니다. 필요하면 담당자에게 문의합니다.

### B.3 CONFIG_BY_DOC_TYPE

특정 doc_type에만 다른 설정을 쓰려면 `CONFIG_BY_DOC_TYPE`에 정의합니다.

```python
# activities/parse/processor.py
    CONFIG_BY_DOC_TYPE = {
        "monimo_news": {"table_text_desc": False},             # 표 설명 LLM 호출 생략
        "product_slf": {"ocr.ocr_mode": "force"},              # 스캔본 OCR 강제
    }
# activities/chunk/processor.py
    CONFIG_BY_DOC_TYPE = {
        "product_slf": {"chunking.chunk_size": 2000},          # 문서 단위 유형의 청크 크기
    }
```

- 키에 쓰는 doc_type도 해당 parse activity에 등록되어 있어야 합니다. 청킹의 `CONFIG_BY_DOC_TYPE`은 청킹 호출에 `params.doc_type`이 넘어올 때만 적용되며([2.1](#21-청킹-단계-수정이-필요한-경우)), 받은 doc_type 문자열을 그대로 비교하므로 공백 없는 소문자로 넘깁니다.
- 값의 키는 설정 경로의 점 표기 또는 같은 뜻의 요청 파라미터 이름입니다. 자주 쓰는 키: 파싱 `enrichment.table_description.enable`(`table_desc`), `enrichment.image_description.enable`(`img_desc`), `enrichment.doc_summary.enable`(`doc_summary`), `enrichment.toc.enable`(`toc`), `ocr.ocr_mode`, `table_text_desc` / 청킹 `chunking.chunk_size`, `chunking.chunk_mode`, `chunking.recursive.chunk_overlap`, `chunking.short_chunk_size`.
- 지원하지 않는 점 표기 키는 경고 후 건너뛰고, 점이 없는 이름은 오타여도 경고 없이 무시될 수 있습니다. 엔드포인트·프롬프트·`min_chunk_size`처럼 기동할 때 읽는 값은 `config.yaml`에서 바꿉니다.

doc_type만으로 구분할 수 없는 조건은 `config_by_condition(job)`에서 같은 형식의 dict를 반환합니다(빈 dict이면 변경 없음).
우선순위는 `config.yaml` → `CONFIG_BY_DOC_TYPE` → `config_by_condition()` → 요청 파라미터 순서이며 뒤에 올수록 우선합니다.

```python
    def config_by_condition(self, job):
        if job.params.get("dept") == "IR":
            return {"enrichment.doc_summary.enable": True}
        return {}
```

### B.4 훅 메소드

`custom_field_*.yaml`은 입력이 예상한 구조일 때 값을 추출합니다. 구조가 다르면 `edit_input`에서 설정이 값을
찾을 수 있도록 입력을 정리합니다.


| 파일    | 훅                                                          | 호출 시점                  | 받는 것                                                    |
| ----- | ---------------------------------------------------------- | ---------------------- | ------------------------------------------------------- |
| parse | `edit_input(ext, doc_type, data, work_dir=None, **kwargs)` | 파싱 전                   | 아래 표 참고                                                 |
|       | `edit_document(job, doc)`                                  | 파싱 후, LLM enrichment 전 | `DoclingDocument` 객체                                    |
|       | `edit_output(ext, doc_type, result, **kwargs)`             | 응답 직전                  | 응답 dict                                                 |
| chunk | `edit_input(kind, data, **kwargs)`                         | 청킹 전                   | `kind=="parse"`이면 `list[dict]`, `"docling"`이면 직렬화된 dict |
|       | `edit_chunk(text, info, **kwargs)`                         | 청크 1건마다                | 본문 str과 `info` dict                                     |
|       | `edit_output(vector_metas, **kwargs)`                      | 응답 직전                  | `GenOSVectorMeta` 목록                                    |





| 파싱 `edit_input`의 처리 경로 | `ext`와 `data`                        | `work_dir` |
| ---------------------- | ------------------------------------ | ---------- |
| JSON 매핑·본문 추출          | `.json`, dict/list(구문 오류이면 원문 str)   | `None`     |
| 엑셀·CSV                 | `.xlsx`(CSV·XLSM 포함), `{시트명: 2차원 행}` | 제공         |
| Markdown·HTML          | 해당 확장자와 원문 str                       | `None`     |
| 그 밖의 파일                | 확장자와 파일 경로 str                       | 제공         |


**공통 규칙**

1. doc_type으로 처리 대상을 제한합니다. 파싱 훅의 `doc_type`은 소문자로 정규화되어 있고, 청킹 훅은 `tb.normalize_doc_type(kwargs.get("doc_type"))`로 비교합니다.
2. 수정할 것이 없으면 입력을 그대로 반환합니다. 바꿀 때는 새 dict·list·문자열을 반환합니다. 입력 객체를 제자리에서 고쳐 반환하면 반영되지 않을 수 있습니다.
3. 요청 파라미터는 `**kwargs`로 받습니다. 일반 훅에는 `job`이 전달되지 않습니다. `job`은 `config_by_condition(job)`·`edit_document(job, doc)`에서만 쓰며(`job.doc_type`, `job.params`, `job.notes` 등), 요청별 상태를 `self`에 저장하지 않습니다.
4. 외부 호출은 `async def`와 비동기 클라이언트로 하고, 동기 I/O는 `await asyncio.to_thread(...)`로 실행합니다.
5. `edit_document`는 enrichment 전에 호출되므로 표 설명 LLM 호출을 줄이려면 여기서 표를 뺍니다. `tb`는 파일 상단에서 import한 toolbox입니다.

**예시 — `monimo_event` 입력 구조가 바뀐 두 경우.** 기준 설정은 `source.records_at: eventList`로 레코드를 찾고
각 필드를 `alias`로 레코드 안에서 찾습니다. 재현용 입력은 `genon/preprocessor/sample_files/drill/`의
`e1_nested_by_company.json`, `e2_detail_joined.json`입니다.

변형 ①은 관계사별로 한 단계 더 중첩된 경우입니다(`{"companyList": [{"mnmFncoCd": "1", "eventList": [...]}, …]}`).
첫 배열의 이벤트만 청크가 되고, `mnmFncoCd`가 레코드 밖에 있어 `GROUP_C`가 모두 기본값이 됩니다. 오류가 나지
않으므로 결과를 확인해야 알 수 있습니다.

```python
    def edit_input(self, ext, doc_type, data, work_dir=None, **kwargs):
        if (ext == ".json" and doc_type == "monimo_event"
                and isinstance(data, dict) and "companyList" in data):
            return {"eventList": [                       # records_at 이 찾도록 eventList 키로 반환
                {**event, "mnmFncoCd": company.get("mnmFncoCd")}
                for company in data["companyList"]
                for event in company.get("eventList") or []
            ]}
        return data
```

변형 ②는 목록(`eventList`)과 상세(`detailList`)가 `cmpId`로만 연결된 경우입니다. 상세 값이 비어 청크 본문에
제목만 남습니다. 같은 훅의 마지막 `return data` 앞에 다음 분기를 추가합니다.

```python
        if (ext == ".json" and doc_type == "monimo_event"
                and isinstance(data, dict) and "detailList" in data):
            detail = {d.get("cmpId"): d for d in data["detailList"]}
            return {**data, "eventList": [
                {**event, **detail.get(event.get("cmpId"), {})} for event in data["eventList"]]}
```

**청킹 `edit_chunk`.** 본문 수정과 청크 제외는 `edit_chunk`에서 합니다. 통계와 순번이 매겨지기 전이므로 자동으로
다시 계산됩니다.

```python
    def edit_chunk(self, text, info, **kwargs):
        if tb.normalize_doc_type(kwargs.get("doc_type")) != "product_slf":
            return text
        if "상담직원용" in text:
            return tb.DROP                     # 이 청크 제외(빈 문자열 반환과 같음)
        if "손실" in text:
            info["fields"]["RISK"] = "high"    # 이 청크에만 실을 값
        return text.replace("■", "")           # 수정한 본문. None을 반환하면 수정 없음
```


| `info` 키         | 값                                                                     |
| ---------------- | --------------------------------------------------------------------- |
| `kind`           | `"docling"`(문서) · `"row"`(레코드/표 행) · `"text"`(그 밖)                    |
| `page` · `index` | 페이지, 0부터 시작하는 분할 순번                                                   |
| `headings`       | 문서 단위 유형의 섹션 경로 목록. `None`일 수 있으므로 `info.get("headings") or []`로 읽습니다 |
| `metadata`       | 문서 또는 레코드 메타데이터. 복사한 값이므로 고쳐도 저장되지 않습니다                               |
| `fields`         | 이 청크에만 실을 값                                                           |


`text`는 접두와 `HEADER:` 줄이 붙은 뒤의 본문입니다. `edit_output`에서 본문을 고치거나 청크를 지웠다면
`tb.refresh_stats(vector_metas)`(본문만 고쳤으면 `reindex=False`)로 통계를 다시 맞춥니다.
`source.merge_rows`, `source.ignore_keys`, front matter 값 가져오기처럼 설정으로 제공되는 기능은 훅에서 다시 구현하지 않습니다.

### B.5 값 변환기와 LLM 응답 파서

LLM이 아닌 방법으로 값을 만드는 `python:` 블록은 [1.6](#16-python-추출기)에 있습니다. 그 밖에 설정에서 이름으로
부르는 확장 지점이 두 가지 있으며, 참조하는 파일은 `config.yaml`과 같은 폴더 아래에 둡니다.

**값 변환기.** 사이트 전용 값 변환은 `processor.py` 최상위에서 등록하고 yaml의 `transform:`에서 이름으로 부릅니다.
등록 코드와 yaml 사용 예시는 [1.7](#17-processorpy-수정이-필요한-경우)에 있습니다.

**LLM 응답 파서.** 모델 응답 형태가 달라 직접 처리해야 하면(예: 결과가 `{"result": {...}}`로 감싸여 오면) `llm` 항목 안에 `parser: {type: python, file: response_parser.py, callable: parse}`를
지정합니다. 함수는 응답 문자열을 받아 dict를 반환합니다.

```python
import json

def parse(llm_output, **kwargs):
    value = json.loads(llm_output)
    result = value.get("result", value)                  # {"result": {...}} 형식이면 안쪽 객체
    if not isinstance(result, dict):
        raise ValueError("LLM 출력은 객체여야 합니다.")
    return result
```

### B.6 청크 메타데이터 추가


| 추가 대상           | 수정 위치                                                     | 비고                                        |
| --------------- | --------------------------------------------------------- | ----------------------------------------- |
| 문서의 모든 청크에 같은 값 | 파싱 `edit_output`에서 `tb.set_chunk_metadata(result, {...})` | `result["metadata"]`에 직접 쓰면 청크에는 실리지 않습니다 |
| 청크마다 다른 값       | 청킹 `edit_chunk`에서 `info["fields"][...]`                   | 본문·통계·순번 필드 이름을 쓰면 청킹이 실패합니다              |
| 적재 컬럼으로 선언      | 청킹 `processor.py`의 `GenOSVectorMeta`                      | 선언하면 타입까지 검사합니다. 선언하지 않아도 실립니다            |


```python
    def edit_output(self, ext, doc_type, result, **kwargs):
        if doc_type == "product_slf":
            tb.set_chunk_metadata(result, {
                "SOURCE_SYSTEM": "CRM",
                tb.FIRST_CHUNK_FIELDS_KEY: ["PRODUCT_NM"],   # 첫 청크에만 붙일 필드
            })
        return result
```

### B.7 제한 사항


| 하지 않을 것                                                                      | 이유                                                                                                                                                      |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `processor.py`끼리 import                                                      | activity별 독립 실행과 교체가 어려워집니다                                                                                                                             |
| `self`에 요청 상태 저장                                                             | 인스턴스는 워커 프로세스마다 activity당 1개이며 동시 작업이 함께 씁니다                                                                                                            |
| `genon/preprocessor/processing/` 또는 docling 수정                               | 릴리스 갱신에서 사라지거나(processing) wheel로 설치되어 수정할 수 없습니다(docling)                                                                                              |
| 파싱 결과 element의 기본 키 삭제·이름 변경                                                 | 청킹이 이 키에 의존합니다                                                                                                                                          |
| rows·records·sections에서 예약 필드(`title`·`created_date`·`appendix` 등)와 같은 필드 이름 | 설정 로딩에서 거부되거나, 훅에서 넣은 값이 덮어써질 수 있습니다([부록 C.2](#c2-청크-출력-스키마)). document의 front matter를 `created_date`로 매핑하는 것은 지원합니다([예시 E](#예시-e-마크다운-문서-product_slf)) |


훅에서 예외를 발생시키면 그 문서의 파싱 또는 청킹 전체가 실패합니다(`error_policy`는 훅에 적용되지 않습니다).
`processor.py` 상단에 import된 `GenosServiceException`을 사용합니다.

```python
raise GenosServiceException(
    error_code='1',
    error_msg='읽을 수 없는 파일입니다.',   # 오류 메시지에 실림
    error_type='permanent',      # transient / permanent / timeout: 재시도 여부 결정
    reason_code='PARSE_D001',    # 선택: 사유 코드
)
```

같은 입력이면 늘 실패하는 오류는 `error_type='permanent'`로 지정해야 재시도하지 않습니다([부록 C.3](#c3-activity-결과와-오류)).
일부 항목만 실패를 허용하려면 예외 대신 해당 항목만 제외하고 경고 로그를 남깁니다.

---

## 부록 C. 결과 형식과 오류

### C.1 파싱 결과 형식


| 입력과 처리 조건                                           | 파싱 결과                                                                                                                   |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 엑셀·CSV에 `rows` 매핑, JSON에 `records`·`sections` 매핑 적용 | `elements` 형식 `{elements: [...]}`                                                                                       |
| 매핑 없는 엑셀·CSV                                        | `processing_mode: tabular`이면 `elements` 형식, `docling`이면 문서로 파싱                                                          |
| PDF·HWP·DOCX·HTML·Markdown 등 문서, JSON 본문 추출 설정 적용   | `output.format: docling`이면 Docling 문서 형식 `{document: {...}}`, `json`이면 `elements` 형식, `html`·`markdown`이면 `content` 문자열 |
| PPT·PPTX                                            | PDF 변환에 성공하면 문서 경로, 실패하면 `elements` 형식                                                                                  |


위 표는 처리기 응답 기준입니다. 스튜디오 단건 실행과 적재 workflow가 저장하는 결과 JSON에서 Docling 문서 형식은 `document` 내부 객체만 저장되므로, 최상위에 `schema_name`·`texts`·`tables` 등이 있습니다. `elements` 형식은 그대로 저장됩니다.

element의 공통 키는 `{category, content, coordinates, id, page}`이며, 행 기반 element에는 `metadata`가 추가됩니다.
청킹은 입력이 문서 객체 자체이거나 `document`가 객체이면 Docling 문서 형식, 그렇지 않고 `elements`가 목록이면 `elements` 형식으로 처리합니다.


| 구분    | Docling 문서 형식                                | 행·레코드형                                    | 그 밖의 `elements` 형식                 |
| ----- | -------------------------------------------- | ----------------------------------------- | ---------------------------------- |
| 분할 방식 | 문서 구조 기반 분할·병합                               | 기본 1건당 1청크. `body.split`이면 긴 본문 분할        | 문자 기반 분할                           |
| 관련 설정 | `chunk_size`, `chunk_mode`, `min_chunk_size` | `body.split`, `body.repeat`, `chunk_size` | `chunking.recursive.chunk_overlap` |


섹션 인식은 정규식이 아니라 파싱 단계가 붙인 제목 라벨로 판정합니다. "제N조" 같은 텍스트 패턴으로 나누어야 하면
담당자에게 요청합니다. 청크 본문이나 경계가 바뀌면 재색인이 필요합니다.

### C.2 청크 출력 스키마

청크 하나가 vector DB 1행이 됩니다. 추가 필드를 허용하므로 선언 없이도 필드와 문서 메타데이터가 실립니다.


| 분류    | 필드                                                                                                                     |
| ----- | ---------------------------------------------------------------------------------------------------------------------- |
| 본문    | `text` (Docling 문서 형식에서 섹션 경로가 있으면 `HEADER:` 줄이 붙습니다)                                                                  |
| 통계    | `n_char` · `n_word` · `n_line`                                                                                         |
| 위치    | `i_page` · `e_page` · `n_page` · `i_chunk_on_page` · `n_chunk_of_page` · `i_chunk_on_doc` · `n_chunk_of_doc` (순번은 0부터) |
| 참조    | `chunk_bboxes` · `media_files` (`elements` 형식은 `"."`일 수 있음)                                                            |
| 문서 메타 | `title` · `reg_date` · `created_date` · `appendix` · `file_path` · `guardrail_categories`                              |
| 표 메타  | `has_table` · `table_refs` · `table_split_index` · `table_split_total`                                                 |


추가 필드가 허용된다고 적재 DB가 자동으로 확장되지는 않습니다. 필드를 추가·삭제하거나 이름·타입을 바꿀 때는
적재 매핑, DB 컬럼, 검색 필터와의 호환성을 확인합니다. rows·records·sections에서는 위 필드와 같은 이름의 필드를 만들지 않습니다. document의 front matter를 `created_date`로 매핑하는 것은 예외로 지원합니다.

### C.3 activity 결과와 오류

activity는 결과 JSON을 `output_ref` 위치에 저장하고, 호출한 쪽에는 요약만 돌려줍니다.


| 키                                      | 뜻                                              |
| -------------------------------------- | ---------------------------------------------- |
| `stage` · `activity` · `ref` · `bytes` | 단계, activity 이름, 결과 위치(`output_ref`), 파일 크기    |
| `count`                                | parse는 요소 수(Docling 문서는 텍스트 항목 수), chunk는 청크 수 |
| `summary` · `preview` · `duration_ms`  | 한 줄 요약, 앞부분 미리보기, 처리 시간                        |
| `chunk_validation`                     | chunk 단계에서 청크 검증에 걸린 것이 있을 때만 포함               |


실패하면 오류에 `type`과 `non_retryable`(재시도하지 않음)이 붙습니다. `details[0]`에는 사유 코드(`reason_code`·`error_category`·`error_kind`)가 실리고, 메시지는
`<activity 이름> <원본 이름 또는 output_ref>: <예외 클래스명>: <error_msg>` 형식입니다.


| 예외                                                                                                                  | `type`              | 재시도 |
| ------------------------------------------------------------------------------------------------------------------- | ------------------- | --- |
| `error_type='timeout'`, `TimeoutError`, `request_deadline` 초과                                                       | `timeout`           | 함   |
| `error_type='transient'`, NFS 일시 오류(`ESTALE` · `EIO` · `ETIMEDOUT` 등)                                               | `transient`         | 함   |
| `error_type='permanent'`, 그 밖의 `OSError`, 입력·설정 오류(`ValueError` · `KeyError` · `TypeError` · `FileNotFoundError` 등) | `permanent`         | 안 함 |
| 워커 프로세스가 재기동을 기다리는 중                                                                                                | `worker_restarting` | 함   |
| 그 밖의 예외(`error_type` 없는 `GenosServiceException` 포함)                                                                 | 예외 클래스명             | 함   |


`strict`에서 보강 단계가 실패하면 메시지 앞에 `[stage]`가 붙으며, 모델 서빙의 연결 오류·HTTP 5xx·429는
`transient`, 시간 초과는 `timeout`, 그 밖의 HTTP 4xx는 `permanent`입니다. 설정 파일을 찾지 못하면 기본값으로
대신하지 않고 항상 오류입니다. activity 폴더에 `config.yaml`이 없으면 그 activity를 실행할 수 없고, 설정에 적은
`custom_field_*.yaml`이나 프롬프트 파일이 없거나 비어 있으면 재시도 없이 실패합니다.

---

## 부록 D. 용어집


| 용어                         | 뜻                                                                                                        |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| 모델 서빙 · 게이트웨이              | LLM·OCR·레이아웃 모델을 API로 제공하는 서비스, 그 호출을 중계하는 진입점                                         |
| 워커(worker) | activity를 실행하는 프로세스. 적재 흐름을 진행하는 pipeline 워커와 파싱·청킹을 실행하는 전처리기 워커가 있습니다 |
| workflow                   | 문서 한 건의 파싱 → 청킹 → embedding → 적재 순서를 정하는 실행 단위                                                           |
| 전처리기 스튜디오 | GenOS 화면에서 activity의 설정·코드를 편집·저장하고 단건 실행하는 도구. 사용 방법은 전처리기 스튜디오 사용 설명서를 봅니다 |
| activity                   | workflow 안에서 워커가 실행하는 처리 단위(파싱·청킹). `activities/<이름>/` 폴더 하나가 activity 하나입니다                                 |
| activity 이름                | activity 폴더 이름. 기본 activity는 `parse` · `chunk`, 복제한 activity는 `parse_<이름>` · `chunk_<이름>`                |
| 복제한 activity               | 기본 activity 폴더를 복사해 만든 activity                                   |
| `processor.py`             | activity 폴더의 처리기 파일. 진입 클래스는 `DocumentProcessor`이며 확장 지점을 제공합니다                                          |
| 훅 메소드(hook)                | `processor.py`에서 오버라이드하면 정해진 시점에 호출되는 메소드(`edit_input` · `edit_document` · `edit_chunk` · `edit_output`) |
| toolbox (`tb`)             | 훅에서 사용할 수 있는 기능 모음. 값 변환기 등록(`tb.register_transform`)과 청크 메타데이터·통계 수정 등에 사용합니다                           |
| doc\_type                  | activity 인자 `params`의 문서 유형 문자열. parse activity의 등록 블록 또는 규칙 파일에 선언한 `doc_type`과 비교합니다                   |
| custom\_fields · 필드        | doc\_type별 값 추출 설정(`custom_field_*.yaml`)과 그 `fields`에 선언한 값. 필드는 청크에 실리며, DB 적재는 적재 매핑과 컬럼을 확인합니다       |
| enrichment                 | 파싱 결과에 필드·요약·설명을 덧붙이는 단계                                                                                 |
| docling                    | 문서 파싱 엔진. wheel로 설치되어 있어 직접 수정할 수 없습니다                                                                   |
| element · 청크(chunk)        | 파싱 결과 `elements` 목록의 한 항목, vector DB에 적재하는 텍스트 단위                                                        |


---

## 부록 E. 지원 요청

다음은 직접 해결할 수 없는 항목입니다. 솔루션 개발자 또는 배포 담당자에게 요청합니다.


| 상황                                                               | 요청할 것                         |
| ---------------------------------------------------------------- | ----------------------------- |
| 모델 서빙 주소·인증키를 모름 | 접속 정보 확인 또는 권한                |
| 모델 접속 실제 값(주소·키)을 바꿔야 함 | 실행 환경의 모델 접속 파일 변경([부록 A.7](#a7-모델-서빙-연결-설정)) |
| 적재 흐름에서 호출할 activity나 `params`(청킹 `doc_type` 포함)를 바꿔야 함          | pipeline workflow 설정 변경       |
| 스튜디오에서 push한 변경이 적재 결과에 반영되지 않음 | 운영 환경 반영(배포) 요청 |
| `genon/preprocessor/processing/`을 고쳐야 할 것 같음                     | 훅 추가(고치기 전에 문의)               |
| `edit_input` 변환으로 처리할 수 없는 새 확장자, 텍스트 패턴 기반 섹션 분할이 필요함           | 처리 경로 추가                      |
| docling 동작을 바꿔야 함                                                | 엔진 수정                         |
| 새 Python 패키지가 필요함                                                | 베이스 이미지 의존성 추가                |
