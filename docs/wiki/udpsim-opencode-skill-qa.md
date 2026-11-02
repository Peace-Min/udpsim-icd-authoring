# OpenCode 대리 모델 Skill QA

2026-10-30, OpenCode 1.19.5의 공식 로컬 세션 API로 무료 모델의 실제 정의 작업을 시험한다.
연결 확인과 별개로, 모델이 만든 중간 정의를 원본 정답·실제 UdpSim Core·패킷 값으로 검사한다.
[환경 관리](udpsim-opencode-api.md), [전체 QA 범위](udpsim-icd-qa.md)를 함께 참고한다.
이후 추가한 입력 8종과 native MCP 실행 준비는 [우선순위 보강](udpsim-priority-qa.md)을 참고한다.
아래 36건은 기존 4종의 역사적 집계이며 새 시나리오의 모델 통과로 확대하지 않는다.

## 시험 방식

모델은 Skill·중간 형식 계약·현재 UdpSim 작성 문서·합성 원본을 받아 JSON을 반환한다.
호스트 하네스가 실제 검증·변환 명령을 실행한다. **OPENCODE_BROKERED_SKILL_QA**이며,
모델이 Claude Code에서 도구를 직접 선택·호출하는 전체 에이전트 시험은 아니다.
사내 Qwen·Claude Code 조합의 인수 상태는 **NOT_RUN**이다.

모델 3종 × 시나리오 4종 × 새 세션 3회, 총 36건을 계획했다.
각 호출은 최대 180초, 시행당 모델 응답 시도는 최대 3회다.
정상 사례는 최초 응답 뒤 최대 2회 재수정하며, 잘못된 seed를 받는 수정 사례는 최대 3회 수정 시도다.
호출 중단·모델 오류는 INFRA_FAILURE로 따로 집계하며 성공률 분모에서 숨기지 않는다.
모델 ID와 무료 가격을 확인하며 유료 모델로 자동 전환하지 않는다.

| 시나리오 | 확인 내용 |
| --- | --- |
| source-nested | big endian, 중첩 구조체·고정 배열·음수·Bits/enum, 장비 송신 → 모의기 수신 |
| document-dependency | 실제 PDF 2-3쪽의 대상 목록/상세에서 1쪽 공통 헤더·enum 참조, little endian·모의기 송신 |
| missing-endian | byte order가 없는 원본에서 추측 없이 BLOCKED, 최종 XML 미생성 |
| repair-length | 실제 검사기가 길이 16을 거절한 진단과 원본을 받아 17로 수정 |

PDF는 선택 가능한 텍스트가 있는 실제 3쪽 파일이며, pypdf로 물리 페이지 표식을 붙여 추출한다.
작은 fixture의 세 페이지를 호스트가 모두 제공한다. **스캔 PDF OCR·이미지 표 인식·모델의
자율 페이지 탐색은 시험하지 않는다.** 렌더링한 세 페이지의 잘림·겹침도 확인했다.

## 판정 기준

정상·수정 사례는 다음을 모두 충족해야 PASS다.

1. 단일 strict JSON, 중복 키·NaN 금지. 실제 중간 정의 검사 통과.
2. 별도 정답과 메시지 방향·ID·길이·필드·타입·배열·비트·enum 대조.
   규격상 유효해도 원본과 다르면 실패하고, 정답을 피드백으로 제공하지 않는다.
   타입/enum 선언 순서와 enum 항목 순서는 wire 순서가 아니므로 이름으로 대조한다.
   원본에 실제로 선언된 미사용 ScanHeader는 필드까지 일치할 때만 추가 선언을 허용한다.
   임의 추가 타입이나 메시지 필드 순서 변경은 허용하지 않는다.
3. 결정적 XML 변환과 실제 UdpSim Core 검사 종료 코드 0, XML_PASS.
4. 독립적으로 계산한 payload를 실제 Core로 해석하여 모든 편집 가능한 leaf의
   PACKET_EXPECTED_MATCH 확인. SEQ가 있는 사례는 기대 SEQ도 별도로 비교한다.
5. 정상 범위의 기대 값 한 개를 바꾸면 Value mismatch와 종료 코드 1이 발생해야 한다.
   도구 미설치나 실행 거부를 이 음성 시험의 성공으로 세지 않는다.

정보 부족 사례는 endian/endianness/byte order 누락을 명시한 BLOCKED만 통과한다.
추측한 big/little을 포함하거나 정상 정의를 완성하면 실패한다.
근거 필드의 존재/형식은 검사하지만 모든 인용의 진실성을 자동 증명하지는 않는다.

실제 시험에서 Nemotron이 SET_WINDOW를 receive로 작성했지만 IR_PASS를 받은 사례가 있었다.
원본의 장비 수신은 컨트롤러 모의기 관점의 send이므로 별도 원본 정답 대조에서 거절했다.
**일반 검증기는 원본 해석의 진실성을 보장하지 않는다.** 이 fixture의 정답 대조는 QA용이며,
새 사내 ICD에 정답이 자동으로 생기는 기능이 아니다. 실제 작업에서는 근거와 원문을 대조해야 한다.

반대로, GLM의 소스 사례에서는 JSON 구문 오류 뒤 타입 선언에 허용되지 않는 evidence를 넣은
응답을 실제 검사기가 unknown_property로 거절했고, 피드백 후 세 번째 응답이 Core/패킷까지
통과했다. 형식 오류의 자동 수정 루프와 원본 의미 오류의 검출 범위가 다른 실제 사례다.

## 실행과 증거

저장소 루트에서 실행한다. Python 3.10+, pypdf, 실제 UdpSim 빌드 도구가 필요하다.
pypdf는 이 PDF 시험 하네스의 의존성이며 런타임 JSON/XML 변환기는 표준 라이브러리만 사용한다.

```powershell
python tools/udpsim_opencode_api.py start
python -m unittest discover -s tests -p test_udpsim_opencode_eval.py
python tests/run_udpsim_opencode_eval.py --model all --repeat 3 --udpsim-root C:/work/UdpSim
```

`--model glm-5.3-flash-free --case document-dependency --repeat 1`로 범위를 줄일 수 있다.
`--resume`은 입력·Skill·평가 도구·UdpSim 소스/문서/커밋 해시가 같은 기존 결과를 재사용한다.
다시 측정하려면 `--work-dir out/<새 이름>`을 사용한다. 이미 기록한 실패를 지우지 않는다.
`--replay-from out/<기존 시험> --work-dir out/<재판정>`은 저장된 응답을 재판정하며 새 모델
응답으로 세지 않는다. 원본/Skill/작업 프롬프트가 다르면 재판정을 거절한다.
선언 순서·미사용 헤더·byte order 동의어의 과도한 정답 비교를 수정한 경우에도 이전 결과와 평가 코드
스냅샷을 보존하고 같은 응답에 실제 Core/패킷 검사를 적용해 별도 기록한다.
Core 검사는 같은 checkout의 빌드 결과를 공유하므로 하네스 안에서 직렬 실행한다.
동일 checkout에 대한 다른 Core 시험 프로세스를 동시에 실행하지 않는다.

기본 증거 위치는 무시되는 `out/udpsim-opencode-eval/`이다.
시행별 프롬프트·반환·세션/모델 ID·중간 정의·실제 명령/종료 코드·XML·양성/음성 패킷
보고서와 최종 summary.json을 보존한다. 원본 정답과 패킷 oracle은 모델에 보내지 않는다.
이전 PING 연결 확인과 예비 시행은 본시험 집계에서 제외한다.

Windows PowerShell 5.1 검증 프로세스에는 `-ExecutionPolicy Bypass`를 명시한다.
시스템/사용자 실행 정책을 영구 변경하지 않는다. 예비 시행에서 발견한 서명 정책 오류는
모델 해석 오류가 아닌 실행 환경 오류로 기록했다.

## 결과

2026-10-30 본시험 **36건, 실제 모델 요청 40회**를 완료했다. 수정 시도도 숨기지 않고 포함한다.
재판정은 같은 40개 응답을 사용했으며 새 모델 호출은 없었다.

| 모델 | PASS / 12 | 원본·응답 오류 | 호출 실패 |
| --- | --- | --- | --- |
| GLM-5.3-Flash Free | **10 / 12** | 0 | 2 |
| Nemotron 3.5 Lightning Free | **7 / 12** | 2 | 3 |
| Flint 40B Free | **1 / 12** | 1 | 10 |

총 **18건 통과, 3건 내용/응답 실패, 15건 호출 실패**다. 호출 실패를 제외한 성공률로
전체 결과를 포장하지 않는다. 세 모델 모두 이 36건의 전 항목 통과 모델은 아니다.

| 시나리오 | GLM | Nemotron | Flint |
| --- | --- | --- | --- |
| 소스 정의 | 3/3 | 1/3 | 0/3 |
| PDF 의존성 | 3/3 | 1/3 | 0/3 |
| 정보 부족 중단 | 3/3 | 3/3 | 1/3 |
| 길이 수정 | 1/3 | 2/3 | 0/3 |

통과한 정상/수정 산출물 **11개**는 모두 실제 **XML_PASS**, 전체 leaf의
**PACKET_EXPECTED_MATCH**, 잘못된 기대 값의 **Value mismatch**를 확인했다.
나머지 통과 **7건**은 정보 부족을 명시한 중단이며 XML/패킷 통과 건수에 넣지 않는다.

내용/응답 실패는 Nemotron의 메시지 ID **18993 → 19025** 오류, PDF 메시지의
**send → receive** 오류, Flint가 누락 사실 대신 `missing fact`라는 일반 문구만 반환한
사례다. 앞의 두 출력은 IR_PASS였지만 원본 대조에서 거절했다. 마지막 사례도 BLOCKED였으며,
이를 실제 정의 완성이나 byte order를 추측한 사례로 과장하지 않는다.

처음의 과도한 평가 기준에서 통과는 15건이었다. source-backed 미사용 ScanHeader 1건과
`wire byte order`라는 올바른 중단 표현 2건을 재판정해 18건이 됐다. 원본의 wire 사실이나
변환기·Core 검증기는 변경하지 않았다. 이전 결과/평가 코드/정답 snapshot은
`out/udpsim-opencode-eval/baseline-harness/`, 재판정 결과는
`out/udpsim-opencode-rejudged/summary.json`에 보존한다.

호출 실패 15건은 당시 클라이언트에 MODEL_TIMEOUT으로 기록됐다. 마지막 GLM 길이 수정
세션에서는 공식 `/session/status`가 **free_tier_limit**을 반환하는 것도 관측했다.
이 한도 관측을 다른 모든 타임아웃의 원인으로 일반화하지 않는다. 한도·초기 기록의 차이는
`out/udpsim-opencode-eval/free-limit-evidence.json`에 남겼다.
현재 클라이언트는 해당 세션의 한도를 발견하면 **MODEL_FREE_LIMIT**으로 저장하고 즉시
중단한다. 이 변경은 모의 회귀 시험으로 확인했으며, 한도 도달 후 새 실모델 호출은 하지 않았다.
유료 모델·유료 구독·다른 계정으로 전환하지 않았다. 무료 서비스의 계속 사용 가능 상태는 아니다.

별도의 Flint `low` 추론 옵션 소스 1회도 180초 안에 완료하지 못했다. 본시험 분모에 섞지 않는다.
서명 정책 문제를 찾은 예비 3회와 기존 PING 연결 확인도 본시험에서 제외했다.
완료된 본시험 응답 25개의 보고 비용은 모두 0이며, 이는 클라이언트가 보고한 값이다.

도구 회귀는 Python **165건** 통과, Skill 형식 검증 통과, Claude plugin/marketplace 검증과
저장소 기본 검사 종료 0을 확인했다. 기존 실제 Core payload 회귀 **25건**은 별도 도구 QA다.
이번 PDF 추출 환경은 Python 3.12.10, pypdf 6.10.2이며 렌더 확인에는 PyMuPDF 1.28.0을 썼다.
UdpSim 기준 커밋은 `26ec9582a4e27c5702258231fb6ac9d6c2499fe3`이고 앱 소스는 변경하지 않았다.

이 작은 합성 시험으로 사내 Qwen의 성능이나 임의 ICD 처리 능력을 보장하지 않는다.
다음 인수 범위는 실제 사내 Qwen·Claude Code의 Skill 발견/도구 실행/중단 복구이며,
스캔 PDF OCR·실제 장비 연동·실제 네트워크 캡처도 이번 시험 범위 밖이다.
