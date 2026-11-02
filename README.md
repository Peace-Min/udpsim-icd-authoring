# udpsim-icd-authoring

ICD PDF 또는 C/C++/C# 패킷 구조체·직렬화 소스에서 **UdpSim 메시지 정의 XML**을 만드는 독립 Skill입니다.
LLM이 원본을 해석하고, 도구가 중간 JSON 검사 → XML 변환 → 실제 UdpSim Core 검증을 수행합니다.
관측 UDP payload가 있으면 바이트·필드 값도 대조할 수 있습니다.

## 호출 방법

### 저장소를 열어서 사용

```powershell
git clone https://github.com/Peace-Min/udpsim-icd-authoring.git
cd udpsim-icd-authoring
claude
```

Claude Code에서 다음 프로젝트 Skill을 호출합니다. clone 후 새 세션에서 시작합니다.

```text
/udpsim-icd-authoring
원본: C:/private/ICD.pdf
범위: PDF 파일 기준 20~30쪽의 메시지
모의기 역할: 제어기
UdpSim: C:/work/UdpSim
출력: C:/private/icd-work/project-a
```

### 다른 프로젝트에서 플러그인으로 사용

```powershell
claude plugin marketplace add Peace-Min/udpsim-icd-authoring
claude plugin install udpsim-icd-authoring@udpsim-icd-authoring
```

설치 후 새 Claude Code 세션에서 호출합니다. 플러그인 이름과 Skill 이름이 같아 아래처럼 표시됩니다.

```text
/udpsim-icd-authoring:udpsim-icd-authoring
```

실제 본체는 [skills/udpsim-icd-authoring/SKILL.md](skills/udpsim-icd-authoring/SKILL.md)입니다.
Codex/다른 에이전트에는 이 파일을 지정하거나, 해당 Skill 폴더 전체를 그 도구가 지원하는
개인 skills 경로로 설치할 수 있습니다. 기존 skillbank에도 같은 이름의 Skill이 있으므로
자동 선택이 혼동되면 사용할 설치본을 하나로 정하거나 플러그인 전체 이름으로 호출합니다.

## 필요한 환경

- **로컬 UdpSim 체크아웃**: 실제 XML 형식과 Core 검증의 기준입니다. 이 저장소에 앱은 포함하지 않습니다.
- **Python 3.10+**: 중간 JSON 검사와 결정적 XML 변환. 이 런타임 도구는 표준 라이브러리만 사용합니다.
- **Windows PowerShell 5.1+, Visual Studio MSBuild/Roslyn, .NET Framework 4.8**: 실제 Core/패킷 검증.
- PDF 읽기/추출 도구는 사용하는 에이전트 환경에 맞게 준비합니다. 스캔 PDF에는 별도 OCR이 필요합니다.

원본 해석이 맞다는 사실까지 형식 검사만으로 증명되지는 않습니다. 근거와 원문을 대조합니다.
실제 ICD·소스·파생 XML·패킷·모델 로그는 Git에 넣지 않습니다. 저장소 내 작업에는 `icd-work/`나 `out/`를 사용합니다.

## 범위와 문서

- [LLM · Agent · Tool 상호작용 시퀀스 다이어그램](docs/wiki/interaction-sequence.md)
- [사용 절차와 예제](docs/wiki/udpsim-icd-authoring.md)
- [QA 범위와 인수 상태](docs/wiki/udpsim-icd-qa.md)
- [입력 12종·도구/체크포인트 QA](docs/wiki/udpsim-priority-qa.md)
- [Codex 자율 완주 결과](docs/wiki/udpsim-codex-autonomous-qa.md)
- [분리 이력과 이 저장소의 검증](PROVENANCE.md)

주요 범위는 메시지 정의이며 시나리오 XML의 전용 자동 생성·검증 QA까지 완료한 Skill은 아닙니다.
UDP payload 검사기는 캡처를 시작하지 않으며 PCAP/PCAPNG는 payload를 별도로 내보내야 합니다.
사내 Qwen·Claude Code 조합 인수는 아직 별도 검증 대상입니다.

## 로컬 검증

```powershell
# 일반 회귀. 외부 모델을 호출하지 않습니다.
python -m unittest discover -s tests -p 'test_*.py'

# Skill/플러그인 형식, 회귀 및 실제 Core/payload까지
powershell -NoProfile -ExecutionPolicy Bypass -File tests/validate.ps1 -UdpSimRoot C:/work/UdpSim

# 추가 합성 입력과 실제 MCP/중단 재개 도구 검사
python tests/validate_udpsim_priority.py --udpsim-root C:/work/UdpSim
```

PDF QA에는 pypdf, fixture PDF 재생성에만 ReportLab이 추가로 필요합니다.
`UDPSIM_QA_ROOT`로 native 단위 검사의 앱 경로를 지정할 수 있으며 기본값은 형제 폴더 `../UdpSim`입니다.
skip된 검사를 통과로 세지 않습니다. OpenCode/Bifrost 도구는 선택적인 외부 QA용이며 사내 Skill 실행의 필수 조건이 아닙니다.

MIT. [Peace-Min/peace-skillbank](https://github.com/Peace-Min/peace-skillbank)에서 이 Skill 관련 파일만 분리했습니다.
