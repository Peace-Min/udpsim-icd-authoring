# LLM · Agent · Tool 상호작용

Agent는 LLM 호출, 도구 실행, 결과 전달과 작업 상태 관리를 맡는 실행 환경입니다.
Claude Code·Codex·OpenCode가 이 역할을 수행합니다. Skill의 지침과 계약은 Agent가 읽어 LLM의 문맥에 제공합니다.

| 역할 | 담당 |
| --- | --- |
| LLM | 원본 해석, 의존성 추적, IR 작성, 도구 선택, 근거에 따른 수정·중단 판단 |
| Agent | 문맥 구성, 도구 요청 실행, 실제 결과의 LLM 전달, 작업 진행·재개 |
| Tool | 파일/PDF 읽기, IR 검사·XML 변환, 실제 Core 검증, 선택적인 payload 검사와 상태 저장 |

아래 Tool은 사용 가능한 읽기/추출 도구와 이 Skill의 스크립트를 묶어 표시했습니다.
일반 사용은 Agent의 파일·셸 도구로 실행하고, 외부 QA에서는 제한된 MCP 어댑터를 사용할 수 있습니다.
MCP 어댑터가 사내 Skill 실행의 필수 구성 요소는 아닙니다.

## 1. 원본에서 검증된 XML까지

아래는 각 검증 게이트를 통과하는 정상 경로입니다. 게이트가 실패하면 다음 단계로 진행하지 않고
두 번째 다이어그램의 피드백 흐름으로 들어갑니다.

```mermaid
sequenceDiagram
    autonumber
    participant LLM
    participant Agent
    participant Tool

    Note over Agent: 사용자 요청에서 원본, 범위, 모의기 역할, UdpSim 경로와 출력 위치 확인
    Agent->>LLM: 작업 요청과 Skill 진입점 제공
    LLM-->>Agent: Skill, 계약과 현재 작성 문서 읽기 요청
    Agent->>Tool: Skill, IR 계약, 현재 UdpSim 작성 문서 읽기
    Tool-->>Agent: 지침과 지원 형식
    Agent->>LLM: 작업 요청과 Skill 문맥 제공
    LLM-->>Agent: 원본 읽기 요청
    Agent->>Tool: PDF 페이지 또는 구조체와 직렬화 소스 읽기
    Tool-->>Agent: 원본 내용과 위치
    Agent->>LLM: 원본과 출처 전달

    loop 공통 헤더, 타입, enum 의존성이 필요한 동안
        LLM-->>Agent: 추가 페이지 또는 참조 소스 읽기 요청
        Agent->>Tool: 요청 범위 밖의 참조 정의도 읽기
        Tool-->>Agent: 참조 정의와 출처
        Agent->>LLM: 의존성 문맥 추가
    end

    LLM-->>Agent: 근거를 포함한 IR JSON 작성 및 저장 요청
    Agent->>Tool: IR 저장
    Tool-->>Agent: 저장 결과
    Agent->>LLM: 저장 결과 전달
    LLM-->>Agent: IR 검증 요청
    Agent->>Tool: icd_tool.py validate
    Tool-->>Agent: IR_PASS와 실제 종료 코드 0
    Agent->>LLM: IR 검증 결과 전달
    LLM-->>Agent: XML 변환 요청
    Agent->>Tool: icd_tool.py convert
    Tool-->>Agent: 생성된 ICD XML과 변환 결과
    Agent->>LLM: 변환 결과 전달
    LLM-->>Agent: 실제 Core 검증 요청
    Agent->>Tool: Test-IcdXml.ps1로 현재 UdpSim 검증기 실행
    Tool-->>Agent: XML_PASS와 실제 종료 코드 0
    Agent->>LLM: Core 검증 결과 전달

    opt UDP payload가 제공된 경우
        LLM-->>Agent: payload 비교 요청과 제공된 기대 값 지정
        Agent->>Tool: Test-UdpPayload.ps1 실행
        Tool-->>Agent: 정확한 패킷 판정과 필드별 바이트, 오프셋, 값
        Agent->>LLM: 패킷 결과 전달
    end

    LLM-->>Agent: 파일 위치, 실제 판정, 미확정 항목과 검사 범위 정리
    Agent->>Tool: 완료 기록과 다음 작업 저장
    Tool-->>Agent: 저장 결과
    Note over Agent: 실제 실행 증거에 맞는 결과를 사용자에게 전달
```

`IR_PASS`는 구현된 형식·일관성 검사 통과이며 원본 해석의 진실성까지 보장하지 않습니다.
XML 생성만으로 `XML_PASS`가 되지 않습니다. 실제 Core 종료 코드가 필요합니다.
payload 기대 값이 없으면 구조 해석만 확인하며, 일부 기대 값만 주면 그 부분만 비교합니다.
실제 캡처·장비 연결과 상대 장비의 정상 동작 확인은 이 흐름의 별도 작업입니다.

## 2. 오류 피드백, 정보 부족과 중단

LLM은 원본에 근거가 있는 오류만 수정합니다. 정보 부족과 환경 실패는 정의를 추측해 채우는 재시도 사유가 아닙니다.
Skill의 수정 상한은 메시지별 최대 3회입니다. QA MCP 어댑터는 최초 후보와 세 번의 실패한 수정 후보 이후 추가 검증을 제한합니다.

```mermaid
sequenceDiagram
    autonumber
    participant LLM
    participant Agent
    participant Tool

    LLM-->>Agent: 저장된 IR 또는 XML 검사 요청
    Agent->>Tool: 실제 검사기 실행
    Tool-->>Agent: 실패 판정, 종료 코드와 진단
    Agent->>LLM: 원본 문맥과 실제 진단 전달

    alt 원본으로 수정 가능한 정의 오류
        loop 최대 3회 수정, 통과하거나 중단 조건이면 종료
            LLM-->>Agent: 원본에 근거한 IR 수정 및 저장 요청
            Agent->>Tool: 수정 IR 저장 후 실제 검사 재실행
            Tool-->>Agent: 현재 판정과 진단
            Agent->>LLM: 최신 결과 전달
            Note over LLM,Agent: IR 통과 후 XML 재생성과 Core 재검증까지 진행
        end
        Note over LLM,Agent: 상한에 도달해도 미해결이면 작업을 중단하고 진단 보존
    else 원본 누락, 충돌 또는 필수 wire 기능 미지원
        LLM-->>Agent: 부족한 사실이나 권위 충돌을 명시하고 BLOCKED 판단
        Agent->>Tool: 미확정 항목과 원본 근거 저장
        Tool-->>Agent: 중단 상태 저장 결과
        Note over Agent,Tool: 최종 XML을 완료로 인정하지 않음
    else 추출기, Python, MSBuild 등 환경 문제
        LLM-->>Agent: 부족한 구성 요소를 명시하고 BLOCKED_ENV 보고
        Agent->>Tool: 현재 산출물과 환경 진단 보존
        Tool-->>Agent: 저장 결과
    else 타임아웃 또는 서비스 한도
        Agent->>Tool: 해당 실행 중단 및 현재 상태 보존
        Tool-->>Agent: 중단 결과와 남아 있는 파일
        Agent->>LLM: 연결이 가능할 때 중단 원인과 저장 상태 전달
        Note over LLM,Tool: 내용의 정답 여부를 판정하지 않고 무한 재시도도 하지 않음
    end
```

패킷 불일치는 원본·IR·XML·캡처와 기대 값을 대조할 계기입니다. 패킷에 맞추려고 정의를 무조건 바꾸지 않습니다.
또한 ID나 송수신 방향을 잘못 해석해도 형식 검사는 통과할 수 있습니다. 실제 QA의 독립 정답 대조는
호스트 평가자가 수행한 절차이며, 새 ICD의 정답을 Tool이 자동으로 만들어 주는 기능은 아닙니다.

## 3. 저장된 상태에서 재개

다음은 QA MCP 어댑터에 구현된 체크포인트 흐름입니다. 일반 Skill 사용에서도 입력/도구 기준과
산출물의 현재성을 확인해야 하지만, 모든 Agent 환경이 이 해시 게이트를 자동 제공하는 것은 아닙니다.

```mermaid
sequenceDiagram
    autonumber
    participant LLM
    participant Agent
    participant Tool

    LLM-->>Agent: 작성한 IR 검증 요청
    Agent->>Tool: IR 검사와 체크포인트 저장
    Tool-->>Agent: IR_PASS와 입력, 도구, 후보 파일의 해시
    Agent->>LLM: 검증 결과 전달
    Note over LLM,Tool: 작업 중단 또는 세션 종료, 파일 상태는 보존

    Agent->>LLM: 새 세션에서 Skill 문맥과 재개 요청 제공
    LLM-->>Agent: 원본, 저장 후보와 체크포인트 읽기 요청
    Agent->>Tool: 저장 파일 읽기와 현재 해시 확인

    alt 입력, 도구와 후보가 저장 당시와 일치
        Tool-->>Agent: 현재 입력과 일치하는 저장 상태
        Agent->>LLM: 재사용 가능한 체크포인트 전달
        LLM-->>Agent: 검증된 후보의 XML 변환 요청
        Agent->>Tool: 현재성 재확인 후 변환
        Tool-->>Agent: XML과 XML_WRITTEN 상태
        Agent->>LLM: 변환 결과 전달
        LLM-->>Agent: Core 검증 요청
        Agent->>Tool: XML 해시 확인 후 실제 Core 검증
        Tool-->>Agent: XML_PASS와 갱신된 체크포인트
        Agent->>LLM: 실제 완료 근거 전달
    else 원본, 도구 또는 산출물이 변경됨
        Tool-->>Agent: STALE_CHECKPOINT, 이전 통과 재사용 거절
        Agent->>LLM: 변경 항목과 재검증 필요 전달
        LLM-->>Agent: 원본 재확인 및 필요한 수정 요청
        Note over LLM,Tool: IR 검사부터 필요한 게이트를 다시 통과해야 함
    end
```

LLM은 파일 상태를 다시 읽어 이어갑니다. 이전 대화가 남아 있다는 가정이나 과거의 완료 문장만으로 재개하지 않습니다.

## 구현과 검증 근거

- [Skill 실행 계약](../../skills/udpsim-icd-authoring/SKILL.md), [오류 분류·수정·payload 흐름](../../skills/udpsim-icd-authoring/references/workflow.md)
- [IR 검사와 변환기](../../skills/udpsim-icd-authoring/scripts/icd_tool.py), [실제 Core 연결기](../../skills/udpsim-icd-authoring/scripts/Test-IcdXml.ps1)
- [패킷 검사기](../../skills/udpsim-icd-authoring/scripts/Test-UdpPayload.ps1), [QA MCP 어댑터의 상태 게이트](../../tools/udpsim_agent_mcp.py)
- [실행 모델과 부모 평가자의 범위를 구분한 자율 완주 QA](udpsim-codex-autonomous-qa.md), [분리본 검증 이력](../../PROVENANCE.md)

이 다이어그램은 현재 메시지 정의 흐름을 설명합니다. 전용 시나리오 XML 생성 QA나 사내 Qwen 인수 완료를 나타내지 않습니다.
