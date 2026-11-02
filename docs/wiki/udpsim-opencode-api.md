# OpenCode 로컬 API로 무료 모델 호출

이 경로는 **현재 작업 세션 → 이 PC의 OpenCode 공식 서버 API → OpenCode 무료 모델**이다.
OpenCode가 세션과 모델 호출을 실행한다. 무료 제공자의 추론 API를 다른 클라이언트로 직접
호출하거나 클라이언트 식별을 위장하는 구성이 아니다.

## 설치와 서비스

Python 3.10+와 Node/npm이 필요하다. OpenCode **1.19.5**를 전역 설정 대신
`out/cloud-qa/opencode`에 설치한다. 서비스는 `127.0.0.1:18090`에만 바인드하고,
XDG 설정·캐시·데이터와 생성물은 무시되는 `out/cloud-qa/opencode-api` 안에 둔다.
기존 사용자 OpenCode 로그인·설정을 가져오지 않는다.

서버의 작업 디렉터리는 그 아래 `workspace`다. 이 폴더는 별도 Git 루트를 사용하며,
요청할 원시 합성 fixture 세 개와 런타임 Skill·진입점만 복사한다. 은행의 평가용
`expected.json`과 평가자 지침 `model-qa.md`는 복사하지 않는다. 모델에게 파일 읽기를
요청할 때는 `fixtures/ping.h`처럼 이 작업 디렉터리 기준 경로를 사용한다.

저장소 루트의 PowerShell에서 다음 관리 명령을 사용한다.

```powershell
python tools/udpsim_opencode_api.py setup
python tools/udpsim_opencode_api.py start
python tools/udpsim_opencode_api.py status
python tools/udpsim_opencode_api.py models
```

이 서버는 컴퓨터 로그인 시 자동 실행되는 시스템 서비스가 아니다. 이 PC를 재시작했거나
관리 도구로 종료했다면 다시 `start`를 실행한다. 포트 충돌·미설치·시작 실패를 성공으로
취급하지 않는다. 종료는 `stop`을 사용하며, 기록한 PID의 실행 파일과 명령을 대조해
다른 작업의 프로세스를 종료하지 않는다.

## 현재 세션에서 호출

현재 작업 에이전트는 관리 도구를 실행하거나 공식 세션 HTTP API를 이용해 호출할 수 있다.
설정된 모델은 무료 후보로 제한한다.

- `flint-40b-free`
- `nemotron-3.5-lightning-free`
- `glm-5.3-flash-free`

```powershell
python tools/udpsim_opencode_api.py ask --model flint-40b-free --prompt "Reply exactly QA_API_OK"
python tools/udpsim_opencode_api.py ask --model nemotron-3.5-lightning-free --prompt-file out/qa-prompt.txt --timeout 120
python tools/udpsim_opencode_api.py ask --model flint-40b-free --prompt "Read fixtures/ping.h once and report the message ID and total length."
```

프롬프트 파일에는 합성 규격·합성 코드만 넣는다. 실제 사내 ICD·구조체·패킷을 무료
외부 모델에 보내지 않는다. 무료 기간의 데이터 이용·보관 조건은 모델마다 다르다.
[무료 모델 조사](udpsim-free-models.md)를 참고한다.

`ask`는 새 OpenCode 세션을 만들고 지정한 모델로 비동기 메시지를 보낸 뒤 응답을
확인한다. 사용자 메시지나 진행 중인 추론만으로 성공을 선언하지 않는다. 완료된 assistant
응답·오류·시간 제한을 구분하며, 제한 시간 초과 시 해당 세션을 중단한다. 자동으로
유료 모델로 바꾸거나 무료 한도 오류를 피하려고 계정을 순환하지 않는다.
공식 세션 상태의 `free_tier_limit`도 확인해 `MODEL_FREE_LIMIT`으로 즉시 중단한다.
다른 세션의 한도 때문에 그 세션을 종료하지 않는다. 2026-10-30 실제 QA 말미에 무료 한도에
도달했으므로 현재 세션에서 추가 무료 추론이 계속 가능하다고 가정하지 않는다.

현재 기본 권한은 읽기·Skill 탐색에 필요한 범위로 제한하며 셸 실행·파일 편집은 허용하지
않는다. 단순 응답 확인은 실제 Skill의 생성·수정·검증 루프를 통과했다는 뜻이 아니다.
본격적인 Skill QA는 합성 원본과 별도의 정답으로 진행하고 실제 Core 검증을 기록한다.

## 사용하는 공식 API

로컬 주소는 `http://127.0.0.1:18090`이다. 아래 경로는 OpenAI Chat Completions API가
아니라 OpenCode 세션 API다.

- `GET /global/health`: 서버 상태·버전.
- `GET /config/providers` 또는 `/provider`: 제공 모델과 설정.
- `POST /session`: 합성 QA 세션 생성.
- `POST /session/{id}/prompt_async`: 모델과 메시지 전달.
- `GET /session/{id}/message`: 응답·오류 확인.
- `POST /session/{id}/abort`: 시간 제한으로 중단.

실제 실행 중인 서버의 `GET /doc`에서 OpenAPI 계약을 확인한다. 다른 버전에서 API 계약이
바뀌면 설치된 서버의 문서를 우선하고 호환 실패를 그대로 보고한다.

## 결과와 한계

메시지 정의·검증·수정 루프의 실제 시험은 [OpenCode Skill QA](udpsim-opencode-skill-qa.md)에
별도로 기록한다. 아래 짧은 응답 확인과 본시험 집계를 혼합하지 않는다.

2026-10-30 실제 설치·연결 기록:

- OpenCode **1.19.5**의 로컬 서버가 `127.0.0.1:18090`에서 실행되고, 공식 health API가
  상태와 버전을 반환했다.
- 현재 세션에서 로컬 API를 통해 **Flint 40B Free**를 호출해 `QA_FLINT_OK` 응답을 받았다.
  반환 모델 ID는 `flint-40b-free`, 제공자는 `opencode`, 완료 사유는 `stop`, 보고된 비용은 0이다.
  이 시험은 연결 확인이며 메시지 정의 Skill QA 통과가 아니다.
- 같은 경로로 **GLM-5.3-Flash Free**에서 `QA_GLM_OK` 응답을 받았다. 반환 모델 ID는
  `glm-5.3-flash-free`, 제공자는 `opencode`, 완료 사유는 `stop`, 보고된 비용은 0이다.
- **Nemotron 3.5 Lightning Free**에서도 `QA_NEMOTRON_OK` 응답을 받았다. 반환 모델 ID는
  `nemotron-3.5-lightning-free`, 제공자는 `opencode`, 완료 사유는 `stop`, 보고된 비용은 0이다.
  이로써 세 무료 후보의 실제 짧은 응답 호출을 모두 확인했다. 대기 시간과 사용 한도는
  실행 시점에 달라질 수 있으며, 세 모델의 Skill 수행 성공을 의미하지 않는다.
- 최종 격리 작업 폴더에서 Flint의 실제 파일 읽기도 확인했다. `fixtures/ping.h`를
  읽고 PING의 ID 17·전체 길이 3·little endian을 반환했으며 assistant 단계는 2개,
  보고된 비용은 0이었다. 원시 연결 결과와 최종 설치 검증 요약은 무시되는
  `out/cloud-qa/opencode-api`에 저장한다.
- 관리 클라이언트 자동 검사 **36건 통과**: 무료 모델·가격 제한, 자격 증명 분리,
  읽기 권한, 기존 서비스·PID 보호, 최신 assistant의 실제 완료 판정, 모델 ID 대조,
  시간 제한·통신 실패의 중단과 결과 저장을 확인했다. 이전 완료 메시지나 미완료
  도구 호출을 현재 최종 응답으로 오판하지 않도록 회귀 검사했다. 잘못된 메시지·assistant
  구조와 비문자열·빈 최종 응답도 실패로 처리하고, 해당 세션의 중단·진단 저장을 확인했다.
  원시 fixture만 복사되는지, 평가 정답·캐시가 제외되는지, 작업 폴더가 별도 Git 탐색
  경계인지와 실제 assistant 단계 수 기록도 검사했다.

초기 은행 루트에서의 파일 읽기 연결 시험에는 모델이 평가 정답을 탐색한 기록이 있어,
블라인드 Skill QA 근거로 사용하지 않는다. 위 격리 작업 폴더에서 재시험했다. 런타임
포맷 문서에도 설명용 PING 예제가 있으므로, 이후 블라인드 QA에는 모델이 보지 않은
새 합성 명세와 별도 정답을 사용해야 한다. 현재 결과는 설치·응답·파일 읽기 연결 확인이다.

자동 테스트는 가짜 HTTP 응답과 프로세스로 정상·음성 경로를 검사한다. 실제 무료 모델
호출 결과는 해당 실행의 모델 ID·완료 상태·응답과 함께 `out/cloud-qa/opencode-api`에
보존한다. 카탈로그에 가격 0이 표시됐다는 사실만으로 실제 호출 성공을 선언하지 않는다.
실제 응답은 보관하되 공유 Wiki에 사내 원본이나 인증 정보를 옮기지 않는다.

무료 모델은 기간 한정이며 사용량 제한·대기·제공 중단이 있을 수 있다. OpenCode의 무료
모델 호출 성공과 사내 Qwen/Claude Code 인수는 서로 다른 결과다. 게이트웨이·클라이언트가
바뀌었으므로 모델 규모가 비슷해도 사내의 전체 동작을 재현했다고 기록하지 않는다.

## 공식 근거

- [OpenCode Server API](https://opencode.ai/docs/server/)
- [OpenCode SDK](https://opencode.ai/docs/sdk/)
- [OpenCode 무료 모델·프라이버시](https://opencode.ai/v2/docs/console/models/)
- [무료 제공자의 외부 클라이언트 제한](https://opencode.ai/v2/docs/console/api/inference/)
