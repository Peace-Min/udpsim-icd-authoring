# UdpSim 클라우드 QA 환경

현재 세션에서 API 키 없이 무료 후보를 호출하려면 [OpenCode 로컬 API 구성](udpsim-opencode-api.md)을
사용한다. 아래 Bifrost·Alibaba 구성은 별도 연결 경로로 보관하며, 무료 OpenCode 모델 호출에는 필요하지 않다.

정확히 같은 모델 대신 비슷한 사양의 무료 모델을 사용할 때는
[OpenCode 무료 모델 사양 조사](udpsim-free-models.md)를 참고한다. 모델 원래 한도와
OpenCode 제공 한도를 구분하며, 사양 조사는 실제 모델 수행 시험 통과를 뜻하지 않는다.

이 환경은 이 PC의 **Claude Code 2.1.312 → 로컬 Bifrost HTTP 2.4.0 → 클라우드 Qwen3.6-27B**
경로를 준비한다. 두 프로그램의 격리 설치와 버전 확인을 완료했다. 기존 사용자 Claude 설치와 전역 설정을 교체하지 않는다. 실제 클라우드 API 키가
없어도 로컬 합성 서버로 게이트웨이 변환·도구 호출·오류 처리를 점검할 수 있다.

## 경로와 실행 구성

- `out/cloud-qa/`: 격리 설치, 생성 설정, 프로세스 상태와 원시 시험 결과. Git에 넣지 않는다.
- mock: `127.0.0.1:18080/anthropic`의 실제 Bifrost, 합성 upstream `127.0.0.1:18082`.
- cloud: `127.0.0.1:18081/anthropic`의 실제 Bifrost, Alibaba Beijing API.
- mock 모델 이름은 `udpsim-mock`이다. 7B 모델을 사내 27B의 대체 모델로 사용하지 않는다.

게이트웨이는 루프백에만 바인드한다. 실제 원본 문서·소스·패킷을 외부 API로 보내지 않고
공유 저장소의 합성 fixture만 시험한다. 설정 파일의 API 키 값은 환경 변수 참조이며,
실제 키를 Git·명령 인자·공유 보고서에 기록하지 않는다.

공급자 경로는 Bifrost의 **Anthropic provider**로 고정한다. mock은 합성 Anthropic Messages
upstream으로, cloud는 Alibaba의 native Anthropic 호환 URL로 연결한다. 이 구성은 OpenAI
Responses API로 우회하지 않는다. 실제 API 키가 디스크 DB에 저장되지 않도록 config store와
log store를 비활성화했다. 이 로컬 구성은 인증 미들웨어를 쓰지 않으므로 루프백 제한을 유지한다.

## 환경 준비와 로컬 점검

저장소 루트의 PowerShell에서 실행한다. Python 3.10+와 Node/npm이 필요하다. 설치 도구는
전역 설치 대신 `out/cloud-qa`에 버전을 고정한다. 준비 과정의 다운로드에는 인터넷이 필요하다.

```powershell
python tools/udpsim_cloud_environment.py setup
python tools/udpsim_cloud_environment.py start --profile mock
python tools/udpsim_cloud_environment.py status
python tools/Test-UdpSimCloud.py --mock --base-url http://127.0.0.1:18080/anthropic --model udpsim-mock --stream --report out/cloud-qa/mock-probe.json
python tools/udpsim_cloud_environment.py claude --profile mock --prompt CLOUD_QA_READ_FIXTURE
```

환경 관리자 명령은 설치·상태를 보고하며, 누락된 바이너리나 포트 충돌을 성공으로 처리하지 않는다.
환경을 종료할 때는 관리자 `stop` 명령을 사용한다. 다른 사용자의 서비스를 임의로 종료하지 않는다.

`Test-UdpSimCloud.py`는 다음을 검사한다.

1. 요청 모델이 게이트웨이 모델 목록에 존재한다.
2. `/v1/messages/count_tokens`가 양의 정수 토큰 수를 반환한다.
3. thinking 블록 뒤의 실제 text 응답을 읽는다.
4. `echo_probe`의 native `tool_use`와 JSON 객체 인자 `{"value":7}`를 확인한다.
5. `--stream`에서는 SSE의 블록 인덱스와 분할 JSON 인자를 조립한다.

mock 성공은 `GATEWAY_MOCK_PASS`다. 이는 실제 Bifrost의 합성 연결 점검이며 모델의 추출 능력이나
사내 통합 인수를 뜻하지 않는다. 텍스트로 출력한 도구 호출 JSON은 native tool 사용으로 인정하지 않는다.
리다이렉트는 따라가지 않으며, 실패 시 기존 성공 보고서를 현재 실패 결과로 교체한다.

## 실제 클라우드 연결

먼저 Alibaba 콘솔에서 **Beijing의 대상 모델 무료 한도·남은 기간**을 확인하고
**Free Quota Only**를 켠다. 도구의 확인 옵션은 사용자의 확인 기록이며, 공급자의 과금 설정을
자동 변경하거나 무료를 보장하지 않는다. API 키는 같은 리전의 키여야 한다.

이 구성에서 쓰는 베이징 native Anthropic Base URL은 `https://dashscope.aliyuncs.com/apps/anthropic`이다.
다른 리전이나 Token/Coding Plan URL을 섞지 않는다. 공급자 설정은
[Alibaba Base URL 안내](https://help.aliyun.com/en/model-studio/base-url), 무료 조건은
[공식 무료 한도 안내](https://help.aliyun.com/en/model-studio/new-free-quota)를 기준으로 확인한다.

환경 관리자의 cloud 시작은 무료 조건 확인과 실제 키 입력이 필요하다. 키는 별도 터미널의
비표시 입력 또는 프로세스 환경 변수 `UDPSIM_CLOUD_API_KEY`로 전달하며 채팅에 붙여 넣지 않는다.

```powershell
python tools/udpsim_cloud_environment.py start --profile cloud --free-quota-confirmed
```

실제 호출 전 해당 터미널에서 다음 확인 값을 설정한다. 이 값은 무료 조건의 자동 검증 결과가 아니다.

```powershell
$env:UDPSIM_CLOUD_FREE_QUOTA_CONFIRMED = '1'
python tools/Test-UdpSimCloud.py --live --base-url http://127.0.0.1:18081/anthropic --model qwen3.6-27b --stream --report out/cloud-qa/cloud-probe.json
```

게이트웨이 인증을 별도로 사용하면 `UDPSIM_GATEWAY_TOKEN`을 프로세스 환경 변수로 전달한다.
공급자 API 키와 로컬 게이트웨이 인증은 다른 값이다. 보고서에는 URL·인증 헤더·원시 오류 본문을
기록하지 않는다. 클라우드 프로토콜 성공은 `CLOUD_PROTOCOL_PASS`이며 Skill 수행 성공은 아니다.

현재 Claude 실행기의 `ANTHROPIC_AUTH_TOKEN=local-gateway-only`는 로컬 연결용 자리표시자다.
실제 Alibaba 키는 게이트웨이 자식 프로세스의 `UDPSIM_CLOUD_API_KEY`이며 Claude에는 전달하지 않는다.
모든 Claude 모델 별칭은 cloud에서 `anthropic/qwen3.6-27b`, mock에서
`anthropic/udpsim-mock`를 가리킨다.

## Skill QA

프로토콜 점검 이후 격리 Claude Code를 환경 관리자의 `claude` 명령으로 시작한다.
mock에서 확인할 수 있는 것은 클라이언트·도구 연결이며 실제 명세 해석의 품질은 실제 27B에서 시험한다.
실제 모델 시험에는 [합성 fixture와 평가 하네스](../../skills/udpsim-icd-authoring/references/model-qa.md)를 사용한다.

무료 한도 확인 후 시작한 cloud 게이트웨이가 살아 있는 상태에서 다음 명령으로 대화형 QA를 연다.
이때 Alibaba 키를 Claude에 다시 입력하지 않는다.

```powershell
python tools/udpsim_cloud_environment.py claude --profile cloud
```

대화형 세션에서 `/udpsim-icd-authoring`을 호출해 합성 fixture를 대상으로 정의·변환·검증을 수행한다.
`--prompt` 인자를 쓰는 비대화형 연결 점검은 `Read`만 허용한 제한 시험이다. 이것으로 XML 생성까지
완료됐다고 판단하지 않는다. 실제 Skill 시험은 정상 권한 흐름의 대화형 세션에서 진행한다.

API 하네스는 `/v1/messages` 응답을 이용한 추출·검증 피드백 시험이다. Claude Code의 스킬 발견·파일
읽기·스크립트 실행·권한 처리는 별도 통합 시험으로 남긴다. 각 결과의 모델 요청/응답 라벨과 실제
버전을 기록한다. 사내 모델의 가중치·양자화·서빙 설정이 아직 미확인이므로 같은 모델 이름만으로
사내 환경과 동일하다고 표시하지 않는다.

## 검증 기록

- `python -m unittest discover -s tests -p test_udpsim_cloud.py`: 합성 HTTP/SSE 및 음성 경로 **23건 통과**.
- `python -m unittest discover -s tests -p test_udpsim_cloud_environment.py`: 가짜 프로세스 핸들을 이용한
  환경 분리·비밀값 미저장·무료 조건 확인·PID 재사용 거부 및 mock Read 결과 검증 등 **16건 통과**.
  프롬프트에 원본 내용을 넣거나 다른 tool ID·오류 결과를 보내는 우회도 성공으로 판정하지 않는다.
  실제 서비스를 바꾸지 않는 시험이다.
- 실제 native Bifrost 2.4.0의 mock 연결 **5개 검사 통과**. 모델 목록·토큰 수·text·native tool·SSE를
  확인했으며 원시 결과는 `out/cloud-qa/probe-native.json`에 있다.
- 격리 Claude Code 2.1.312에서 실제 `Read` 도구 호출 후 결과를 게이트웨이로 돌려보내는
  **2턴 왕복을 확인했다**. 이 합성 연결 시험은 Skill 전체 수행 시험이 아니다.
- 실제 클라우드 27B와 사내 게이트웨이 인수는 API 키·환경을 갖추고 수행하기 전까지 **NOT_RUN**이다.

Claude JSON에 나타나는 `total_cost_usd`는 합성 사용량에 대한 클라이언트 추정치일 수 있다.
mock 시험의 클라우드 청구액으로 해석하지 않는다. 실제 비용·무료 잔여량은 Alibaba 콘솔을 기준으로 확인한다.

진단 코드는 모델 미노출, 토큰 수 형식 오류, 비-native 도구 호출, 잘못된 도구 인자, 잘린 SSE,
타임아웃, HTTP 오류를 구분한다. 본문에 사내 데이터가 들어갈 수 있는 실제 공급자 오류는 그대로
공유 보고서에 복사하지 않는다.
