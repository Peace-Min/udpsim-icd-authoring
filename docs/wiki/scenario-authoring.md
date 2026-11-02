# 시나리오 초안 생성

0.2.0에서 독립 Skill에 추가한 기능이다. **UdpSim 앱과 XML 형식은 유지**하고, 기존 ICD/Config에서
실제 Core가 계산한 필드 목록을 가져와 시나리오 JSON 계획과 XML 초안을 만든다.

사용자는 어떤 메시지를 어느 장비에 어떤 값으로 언제 보낼지 정한다. LLM은 그 의도를 계획에
옮기고 도구를 실행한다. Tool이 주기·대상·시험 값의 운영 의도를 스스로 결정하지 않는다.

## 지원 범위

| 종류 | 사용자가 정하는 내용 |
| --- | --- |
| Periodic | Send 메시지, 대상, 주기, 시작 지연, 모든 본문 값 |
| Manual | Send 메시지, 대상, 모든 본문 값 |
| Response | Receive 트리거, 본문 조건, 응답할 Send 메시지, 대상, 지연, 모든 본문 값 |

조건은 모두 일치해야 하며 빈 조건은 해당 트리거를 항상 받는 경우다. 임의 순서의 wait/timeout/retry,
반복 횟수·상태 전이·분기 스크립트는 현재 앱에 없는 기능이라 이 도구에서도 만들지 않는다.
Config의 주소/포트와 사용 여부는 기존 Config에 있어야 한다.

## 세 단계

1. `Export-ScenarioContext.ps1`: 실제 앱의 strict Config/ICD 검사를 통과한 뒤 Core의 카탈로그에서
   정확한 ICD 키, 사용 장비, 송수신 코드, 전개된 본문 leaf·수동 헤더·자동 헤더, enum/폭을 내보낸다.
2. `scenario_tool.py`: `catalog`/`fields`로 확인하고 `template`으로 필수 값 null인 계획을 만든다.
   LLM/사용자가 의도를 채운 뒤 `generate`로 XML 초안을 생성한다. 파일·도구 해시가 바뀌었으면 재수출한다.
3. `Test-ScenarioXml.ps1`: 원래 UdpSim `ValidateXml.ps1 -ConfigPath ... -ScenarioPath ... -StrictConfig`를
   실행한다. 실제 종료 0만 SCENARIO_PASS다. 소켓을 열거나 입력을 고치지 않는다.

경로와 전체 JSON 계약은 [시나리오 reference](../../skills/udpsim-icd-authoring/references/scenario-authoring.md)에 있다.
Skill 호출명은 기존과 동일하다. [README 예제](../../README.md#시나리오-초안-생성)를 참고한다.

## 생성 규칙

- 본문 leaf는 배열/Bits 경로까지 **전부 정확히 한 번** 필요하다. 값은 문자열이며 null/누락을 0으로 채우지 않는다.
- 수동 헤더는 선택이다. 생략하면 앱의 0 기본값을 사용하며 생성 결과에 해당 경로를 보고한다.
- id/length/seq 자동 헤더는 지정할 수 없다. Response 조건에는 Receive 본문만 쓸 수 있다.
- Send/Receive 방향, Config의 ICD 키와 장비 이름은 실제 카탈로그와 대소문자까지 맞아야 한다.
- 다른 ICD의 장비나 미사용 장비는 대상이 될 수 없다. `*`도 해당 ICD의 사용 장비가 있어야 한다.
- 출력은 UTF-8 BOM·CRLF·2칸 들여쓰기다. 실패한 생성은 이전 파일을 보존하지만 그 파일이 새 요청의 성공 증거는 아니다.
- 최초 템플릿의 지연 0·enabled=true는 명시된 앱/UI 기본값이며 필요하면 의도에 따라 바꾼다.
  targets·period·본문 값은 확정 전 null이다. 해시가 다른 context/plan은 재사용하지 않는다.

## 검증 범위

단위 검사는 계획/필드/값/대상/시간/출력 계약을 다룬다. 실제 통합 검사는 독립 합성 ICD 두 개,
상대 icdBaseDirectory, 미사용 장비, 중첩 배열/Bits/enum과 수동 헤더를 사용한다.
세 종류를 합친 시나리오를 실제 Core로 로드하고 누락 값·Config 오타·도구 부재·입력 변경도 검사한다.

2026-11-02 기준 전체 Python **218개**, 그중 시나리오 단위 검사 **25개**, 실제 Core 연계
시나리오 검사 **24개**가 통과했다. 독립 Codex 에이전트도 합성 Config/ICD와 사용자 요청만 받아
세 종류를 생성했다. 별도 비교에서 값·대상·주기·조건·헤더 생략을 확인하고 실제 strict Core 검사를 통과했다.
도구 변경 후 오래된 context의 거부와 재수출 후 재검증도 확인했다.
반입 패키지도 별도 경로에 압축 해제해 파일 176개의 해시를 확인하고 같은 시나리오 검사 24개를 통과했다.

```powershell
python -m unittest discover -s tests -p test_scenario_tool.py
python tests/validate_scenarios.py --udpsim-root C:/work/UdpSim
```

이는 정의/도구 검증이다. 실제 장비 응답, 모의기 실행 중 동작과 사내 Qwen·Claude Code 수행을
통과시킨 것이 아니다. 기존 메시지 정의의 [역사적 QA 결과](udpsim-codex-autonomous-qa.md)와도 분리한다.
