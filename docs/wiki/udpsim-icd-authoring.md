# UdpSim 메시지 정의 Skill

ICD PDF 또는 C/C++/C# 패킷 정의 소스를 읽어 근거가 남는 중간 JSON을 작성하고,
결정적 도구로 UdpSim ICD XML을 생성·검증한다. 원본 해석은 모델의 작업이며,
중간 정의와 XML의 형식·내부 일관성은 실행 도구가 검사한다.

이 페이지는 사용 절차다. [QA 범위와 실제 결과](udpsim-icd-qa.md),
[제작 계획](../plans/udpsim-icd-authoring-plan.md),
[실행 계약](../../skills/udpsim-icd-authoring/SKILL.md)을 함께 참고한다.

## 준비와 오프라인 반입

- 이 독립 저장소의 `skills/udpsim-icd-authoring/`와 사용할 진입점.
- 현재 UdpSim 전체 체크아웃. 최초 기준 커밋은
  `26ec9582a4e27c5702258231fb6ac9d6c2499fe3`이며, 실행 시 실제 커밋도 기록한다.
- Python **3.10 이상**. JSON/XML 도구는 표준 라이브러리만 사용하며 pip 설치는 없다.
  사내에 Python이 없으면 승인된 오프라인 설치본 또는 실행 환경을 함께 준비한다.
- Windows PowerShell **5.1 이상**, Visual Studio MSBuild/Roslyn,
  **.NET Framework 4.8**. MSBuild 위치가 기본값과 다르면 `-MSBuildPath`를 지정한다.
- PDF 입력이면 실제로 사용 가능한 로컬 PDF 읽기/텍스트 추출 도구.
  스캔본에는 별도의 로컬 OCR이 필요하다. Skill에는 PDF/OCR 엔진이 번들되지 않는다.
  추출할 수 없으면 해당 단계는 `BLOCKED_ENV`로 보고하며 문서 내용을 지어내지 않는다.

인터넷 연결이나 자동 설치를 전제로 하지 않는다. 실제 ICD·소스·파생 XML·패킷·모델
입출력은 공개 저장소가 아닌 승인된 작업 경로에 둔다. 저장소 안에서 작업한다면
무시되는 `icd-work/` 또는 `out/`를 사용하고 Git 제외 여부를 확인한다.

반입용 개발 스냅샷은 저장소 루트에서 아래 명령으로 만들 수 있다.

```powershell
& ./tools/package-udpsim-skill.ps1 -UdpSimRoot 'C:/work/UdpSim'
```

기본 출력은 무시되는 `out/udpsim-transfer/`의 ZIP이다. 명시된 소스 목록만 담으며
Skill·합성 시험·관련 문서와 UdpSim Core/검증기/작성 예제를 포함한다. manifest에
파일별 SHA-256과 두 저장소의 기준 커밋을 기록한다. 미커밋 개발 변경을 포함할 수
있으므로 전체 플러그인 배포본이나 커밋 자체와 동일한 파일 집합으로 보지 않는다.
Python 실행 환경·모델 가중치·캡처 드라이버·인증 정보는 포함하지 않는다.
압축을 푼 뒤 `START-HERE.md`에 따라 필수 실행 환경을 별도로 준비하고 시험한다.

## 호출

체크아웃 루트에서 Claude Code를 시작하면 프로젝트 진입점
`/udpsim-icd-authoring`을 사용한다. 플러그인 설치에서는
`/udpsim-icd-authoring:udpsim-icd-authoring`을 사용한다. 명령이 보이지 않으면 세션을
재시작하거나 사용 중인 버전에서 지원하는 플러그인 다시 읽기를 수행한다.
이 문서는 특정 Claude 버전에서 명령 발견까지 검증했다는 뜻은 아니다.

Codex나 다른 에이전트에서는 `skills/udpsim-icd-authoring/SKILL.md`의 위치를 직접
주거나 해당 스킬 폴더를 지원하는 skills 경로로 복사한다. 독립 모델도 같은
입출력 파일과 도구 명령을 사용할 수 있다.

### PDF 입력 예

```text
/udpsim-icd-authoring
원본: C:\private\EquipmentICD.pdf
범위: PDF 파일 기준 40~55페이지의 메시지. 인쇄된 쪽수와 구분해줘.
모의기 역할: 제어기
UdpSim: C:\work\UdpSim
출력: C:\private\icd-work\equipment-a
먼저 메시지 목록을 뽑고, 공통 헤더·타입·enum의 범위 밖 참조도 따라가줘.
불명확한 필수 정보는 추정하지 말고 확인 필요로 남겨줘.
```

메시지 목록 페이지는 작업 대상을 찾는 시작점이다. 상세 정의와 참조 타입 없이
목록만으로 XML을 완성하지 않는다. 페이지별 근거와 실제 추출 가능 여부를 남긴다.

### 소스 입력 예

```text
/udpsim-icd-authoring
원본: C:\private\Protocol
범위: StatusPacket, ControlPacket 및 관련 직렬화 코드
모의기 역할: 제어기
UdpSim: C:\work\UdpSim
출력: C:\private\icd-work\equipment-b
참조 타입·상수·enum과 실제 바이트 순서 변환까지 확인해줘.
```

구조체 선언·`sizeof`·packing·컴파일러 비트필드만으로 전송 배치를 확정하지 않는다.
실제 직렬화 경로를 확인한다. 문서와 소스가 상충하면 기준 원본을 정하기 전까지
자동으로 합치지 않는다.

## 생성과 검증

아래 명령은 저장소 루트 PowerShell에서 실행하는 예다. 원본 분석 결과를 먼저
`definition.json`으로 작성한다. 계약은
[중간 정의 형식](../../skills/udpsim-icd-authoring/references/intermediate-format.md)을 따른다.

```powershell
$skill = Join-Path (Get-Location) 'skills/udpsim-icd-authoring'
$work = 'C:/private/icd-work/equipment-a'
python "$skill/scripts/icd_tool.py" validate --input "$work/definition.json"
python "$skill/scripts/icd_tool.py" convert --input "$work/definition.json" --output "$work/device.icd.xml"
& "$skill/scripts/Test-IcdXml.ps1" -UdpSimRoot 'C:/work/UdpSim' -IcdPath "$work/device.icd.xml"
```

각 단계가 성공한 뒤에 다음 명령으로 진행한다. 중간 정의 검사는 누락·미확정
정보·잘못된 타입·중복·길이·비트 겹침 등을 검사한다. XML 최종 검사는 실제 UdpSim
`tools/xml/ValidateXml.ps1`을 사용한다. 출력 파일이 존재한다는 사실만으로 통과라고
판정하지 않는다. Config/시나리오까지 요청하면 UdpSim 문서에 따라 작성하고 기존
검증기에 `-StrictConfig`로 함께 검사한다.

원본에서 고칠 수 있는 오류만 수정하고 메시지별 최대 **3회 수정 라운드** 후 멈춘다.
원본 부족·상충·미지원 요구는 재시도로 해결하지 않는다. 원본 위치와 기준 커밋,
대상 목록, 중간 정의, 미확정 항목, 실제 명령·종료 코드·진단, 다음 작업을 작업 폴더에
남겨 중단 후 이어간다. 검증기·스키마·앱 코드를 바꿔 통과시키지 않는다.

## 실제 패킷 바이트 확인

캡처 도구에서 **UDP payload만** hex 텍스트나 binary 파일로 내보낸 뒤 검사한다.
Ethernet/IP/UDP 헤더가 붙은 프레임 전체, PCAP/PCAPNG 파일을 직접 입력하지 않는다.
캡처와 장비 연결은 이 검사기의 기능이 아니다.

```powershell
& "$skill/scripts/Test-UdpPayload.ps1" `
  -UdpSimRoot 'C:/work/UdpSim' -IcdPath "$work/device.icd.xml" `
  -PayloadPath "$work/observed.hex" -Format hex -Message 'STATUS' `
  -ExpectedPath "$work/expected.json" -ReportPath "$work/packet-result.json"
```

기대 값 파일은 `{"Channels[0].Value":"12"}` 같은 leaf 경로와 문자열 값의 JSON
객체다. 실제 Core의 배치와 코덱으로 메시지 ID·길이·오프셋·원시 바이트·해석 값을
확인하고 지정한 기대 값과 비교한다. 자세한 형식은
[패킷 검증 안내](../../skills/udpsim-icd-authoring/references/packet-validation.md)를 따른다.

기대 값을 주지 않은 구조 검사는 모든 필드가 의도한 값이라는 보장이 아니다.
기대 값 일부만 주면 그 부분만 비교한 것이다. 캡처에 잡힌 사실과 장비의 정상
처리도 다르다. 패킷과 맞지 않는다고 원본 정의를 무조건 패킷 쪽으로 고치지 않는다.
UDP payload만으로는 상대 주소·포트·모의기 역할에 따른 송수신 방향을 증명할 수 없다.
방향은 원본과 모의기 역할을 대조하고, 필요하면 별도 캡처 메타데이터로 확인한다.

## 결과 읽기

- `IR_PASS`: 중간 정의가 구현된 검사에 통과했다. 원본 해석의 정확성은 별도다.
- `XML_PASS`: 해당 XML에 실제 UdpSim 검증기가 종료 코드 0을 반환했다.
- `PACKET_DECODE_PASS`: 관측 payload의 ID·길이가 맞고 필드 해석이 성공했다.
- `PACKET_EXPECTED_SUBSET_MATCH` / `PACKET_EXPECTED_MATCH`: 지정한 기대 값 일부 또는
  모든 편집 가능한 leaf가 일치했다. SEQ는 `-ExpectedSeq` 지정 시에만 비교한다.
- `TARGET_MODEL_PASS`: 실제 사내 모델과 Claude Code 조합의 별도 인수 시험 통과.
  앞의 통과 상태가 이 상태를 대신하지 않는다.
- `NOT_RUN` / `BLOCKED_ENV`: 미실행 또는 실행 환경 부족. 통과 수에 포함하지 않는다.

최종 전달에는 파일 위치·검증 결과·미확정 요구·검사하지 못한 범위를 남긴다.
로더 통과는 실제 포트 바인드나 상대 장비 적합성을 보장하지 않는다.
