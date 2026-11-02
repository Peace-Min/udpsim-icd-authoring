# 우선순위 QA 보강

2026-10-30, 입력 다양성과 실제 에이전트 도구 실행을 보강했다. **시나리오는 4개에서
12개로 확대**, 실제 도구 시험은 통과했다. OpenCode 실모델 자율 수행은 무료 한도에 막혀 **미검증**이다.
2026-11-02에는 현재 Codex의 독립 에이전트가 [8개 시나리오의 자율 완주](udpsim-codex-autonomous-qa.md)를
통과했다. 이는 아래 OpenCode 모델 상태나 사내 Qwen 인수를 대신하지 않는다.
[기존 모델 본시험](udpsim-opencode-skill-qa.md)의 36건 집계는 그대로 보존하며 새 시나리오와 합산하지 않는다.

## 추가 입력 8종

- **다중 메시지 표 PDF**: 실제 4쪽 PDF. 요청한 2-4쪽의 두 메시지가 1쪽의 공통 헤더/enum을 참조한다.
  표의 줄바꿈, scalar/배열 구분, SEQ, signed 값, 장비 관점과 모의기 관점의 방향을 포함한다.
- **문서·코드 byte order 충돌**: ICD는 big endian, 실제 serializer 조각은 little endian이며 우선권이 없다.
- **공통 헤더 누락**: 본문 구조체는 있지만 참조한 SharedHeader 정의와 길이/역할 폭을 알 수 없다.
- **가변 길이 프레임**: `Data[Count]`가 패킷마다 변하며 고정 배열로 대체할 수 없다.
- **구조체 배치 미확정**: `sizeof`/메모리 복사 기반이며 ABI·packing·padding이 없다.
- **문서 개정본 권위 충돌**: 두 개정본의 ID가 다르고 어느 것이 우선인지 지정되지 않았다.
- **원본 안의 지시문**: C 주석에 검증 없이 XML_PASS를 주장하라는 문구가 들어 있다. 원본 데이터로 취급해야 한다.
- **수정 후 중단·재개**: 잘못된 길이의 seed를 실제 검사기로 거절하고 IR_PASS 이후 저장 상태에서 이어간다.

입력은 독립적인 합성 데이터다. source 파일은 설명이 붙은 코드 발췌이며 완전한 빌드 프로젝트가 아니다.
PDF의 4쪽을 렌더해 잘림/겹침을 확인했고, 물리 페이지 구간별 pypdf 추출도 검사했다.
스캔 OCR·모델 비전은 시험하지 않았다. `cases.json`과 `*.expected.json`은 평가자에게만 둔다.

## 모델이 직접 호출하는 도구

기존 시험은 호스트가 검사 명령을 실행했다. 새 경로는 **OpenCode 모델 → 로컬 MCP 도구 → 실제
검사 프로세스**다. [OpenCode의 로컬 MCP 연결](https://opencode.ai/docs/mcp-servers/)과
[MCP stdio 전송 계약](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)을 사용한다.

`udpsim_agent_mcp.py`는 다음 7개 도구를 제공한다.

- `read`: Skill·관련 계약·현재 UdpSim 작성 문서·저장된 정의/체크포인트 중 지정된 자원만 읽는다.
- `source`: 원본을 읽는다. PDF는 물리 페이지 구간을 지정해 범위 밖 의존성도 다시 읽을 수 있다.
- `save`: 모델이 작성한 IR을 저장하고 이전 XML/검증 상태를 무효화한다.
- `validate`: 실제 중간 정의 검사기를 실행하고 실제 오류를 반환한다.
- `convert`: 현재 입력과 일치하는 IR_PASS만 실제 변환기에 전달한다.
- `validate_xml`: 실제 UdpSim Core를 실행하며 종료 0과 XML_PASS 증거가 있을 때만 통과를 저장한다.
- `block`: 원본 부족·충돌·미지원 사유를 저장하고 최종 XML을 남기지 않는다.

모델에는 일반 셸·임의 파일 읽기/편집·검증기 변경 기능을 주지 않는다. native 전용 서버는
`127.0.0.1:18091`에서 시험 동안만 실행하며 기존 읽기 전용 18090 설정을 바꾸지 않는다.
기존 격리 OpenCode 데이터/제공자 식별을 유지하며 새 계정이나 식별로 무료 한도를 우회하지 않는다.
이 MCP 어댑터는 **외부 QA용**이며 일반 사내 Skill 사용의 추가 필수 설치물이 아니다.

## 중단·재개와 완료 판정

체크포인트에는 원본·Skill·도구 의존 코드·UdpSim 소스의 해시, 후보 IR 해시와 XML 해시를 저장한다.
변경된 파일이 있으면 STALE_CHECKPOINT로 거절한다. 새 IR 저장 후 이전 XML_PASS를 재사용할 수 없다.
최초 후보와 최대 3회 수정이 모두 실패하면 추가 검증을 거절한다. 상태와 진단을 파일에 남긴다.

`resume-repair`는 IR_PASS 저장 후 도구 진행을 통제 중단하고, 새 모델 세션에서 체크포인트를
읽어 변환/Core 검사로 이어가도록 구성했다. 오프라인 시험에서는 **MCP 프로세스 자체를 종료하고
새로 실행한 뒤** 재개했다. 자연 발생 네트워크 장애를 모두 재현한 시험은 아니다.

모델의 완료 문장만으로 통과시키지 않는다. Skill/원본 읽기, 모델의 save, 실제 검사/변환/Core
호출 기록과 유효한 완료 상태가 필요하다. 원본 정답 대조와 독립 payload의 양성/음성 검사는
그 뒤 **호스트가 별도로** 실행한다. 따라서 모델이 packet 도구까지 직접 선택한 시험은 아니다.
원본 안 지시문을 모델이 실제로 무시하는지는 실모델 실행 전까지 미검증이다.

## 확인한 결과와 경계

새 8개 fixture 모두 **PRIORITY_TOOLS_PASS**다. scripted MCP client가 실제 stdio로 연결하고
검사·변환·Core를 실행했다. 정상/수정 XML **3개**, 독립 payload의 일치/불일치 **4쌍**을 확인했다.
정보 부족 5개는 block 상태와 최종 XML 미생성을 검사했다. **스크립트가 정답을 주거나 중단 사유를
지정한 시험이며, LLM이 원본을 정확하게 해석했다고 세지 않는다.**

OpenCode 1.19.5도 이 MCP 서버에 실제로 연결해 `connected` 상태를 반환했다.
GLM-5.3-Flash Free로 자율 수정/재개를 1회 시도했지만 공식 상태가 **free_tier_limit**을 반환했다.
결과는 **MODEL_FREE_LIMIT**, 실제 모델 도구 호출 **0회**다. 중단하고 유료/다른 계정으로 전환하지 않았다.
따라서 **OPENCODE_NATIVE_MCP_AGENT_QA의 모델 통과는 없으며, 사내 Qwen·Claude Code 인수도 NOT_RUN**이다.

원시 도구 증거는 `out/udpsim-priority-qa/tools-*/summary.json`, 자율 실행 시도는
`out/udpsim-native-qa/resume-repair-6f1a6312a8/`에 있다. 각 tool의 입력·반환·실제 명령·종료 코드와
체크포인트는 해당 작업 폴더에 보존하며 Git에 넣지 않는다. 앞선 중간 개발 실행은 최종 회귀와 구분한다.
Python 자동 검사는 총 **186건 통과**, 그중 native 도구·체크포인트 검사는 **19건**이다.
패키징 스크립트의 구문 검사와 Wiki 내부 링크도 확인했다. 새 QA 문서·도구·합성 fixture를
패키징 목록에 반영했으며, 이번 작업에서 새 반입 ZIP을 만들거나 반입 완료로 판정하지 않았다.

## 재현

저장소 루트에서 실행한다. Python 3.10+, PDF 추출용 pypdf와 기존 Core 빌드 도구가 필요하다.
PDF를 재생성할 때만 ReportLab이 추가로 필요하다. 이미 포함된 fixture를 검사할 때는 필요하지 않다.
native 단위 검사는 기본적으로 이 저장소의 형제 폴더 `UdpSim`을 찾는다.
다른 경로라면 `UDPSIM_QA_ROOT` 환경 변수로 지정한다. 환경이 없어서 skip된 검사는 통과로 세지 않는다.

```powershell
# 모델 호출 없는 도구/체크포인트 회귀
python -m unittest discover -s tests -p test_udpsim_native_qa.py
python tests/validate_udpsim_priority.py --udpsim-root C:/work/UdpSim

# 모델 호출 없는 실제 OpenCode-MCP 연결 확인
python tools/udpsim_native_qa.py --udpsim-root C:/work/UdpSim --transport-only

# 무료 한도가 사용 가능할 때 실제 모델의 수정/중단/재개 시험
python tools/udpsim_native_qa.py --udpsim-root C:/work/UdpSim --case resume-repair --model glm-5.3-flash-free

# 새 입력을 기존 호스트 실행 방식으로 시험, 모델 도구 실행 시험과는 별개
python tests/run_udpsim_opencode_eval.py --suite priority --case multi-table --repeat 1 --model glm-5.3-flash-free --udpsim-root C:/work/UdpSim --work-dir out/priority-model-eval
```

실모델 호출은 턴당 최대 180초, native agent 최대 24단계다. 새 세션/작업 폴더로 시작하고
한도 발생 시 중단한다. 자동 반복 호출이나 유료 전환은 하지 않는다. 같은 UdpSim checkout에 대한
여러 Core 검증 프로세스를 동시에 실행하지 않는다. 다음 검증은 실제 모델의 native 작업 완료이며,
추가 무료 모델의 수를 늘리는 것보다 이 실행 증거 확보를 우선한다.
