# OpenCode 무료 모델 사양 조사

확인일: 2026-10-30. 비교 기준은 사내 문서의 Qwen3.6-27B, 컨텍스트 262,144토큰이다.
Qwen3.7 Plus/Max와 혼동하지 않는다. 모델의 유사 사양을 허용한다는 사용자 조건을 반영했다.

## 확인 방법과 한계

공식 무료 목록과 개발사 모델 카드를 조사하고, 이 PC에 격리 설치한 OpenCode 1.19.5에서
`opencode models opencode --verbose`를 실행했다. 아래 OpenCode 한도·입력·기능·가격은
그 명령이 표시한 카탈로그 값이다. 실제 장문 한도나 모델 추출 품질을 시험한 결과는 아니다.
로그인·결제 수단 연결·유료 모델 호출은 하지 않았다.

공개 카탈로그 원시 결과와 요약은 무시되는 `out/cloud-qa/`에 보관한다.
`opencode-free-model-summary.json`에는 버전·확인일·모델별 설정과 `inference_tested=false`가 있다.
다른 버전이나 향후 카탈로그에서는 값이 바뀔 수 있다.

## 우선 비교 후보

| 모델 | 공개 구조·파라미터 | OpenCode 컨텍스트 | OpenCode 최대 출력 | 입력 |
| --- | --- | --- | --- | --- |
| 사내 Qwen3.6-27B, 비교 기준 | Dense, 약 27B | 사내 측정 262,144 | 사내 미확인 | 사내 이미지 입력 미확인 |
| Flint 40B Free | MoE, 총 39.8B / 활성 약 2.5B | 262,144 | 65,536 | 텍스트 |
| Nemotron 3.5 Lightning Free | 하이브리드 MoE, 총 30B / 활성 3B | 262,144 | 262,144 | 텍스트 |
| GLM-5.3-Flash Free | MoE, 총 320B / 활성 18B | 200,000 | 32,000 | 텍스트·이미지·비디오 |

세 후보 모두 현재 OpenCode 목록에서 추론·도구 호출을 지원하며 입력·출력 가격이 0이다.
최대 출력은 총 컨텍스트와 독립적으로 전부 사용할 수 있다는 뜻이 아니다. 입력·추론·출력의
공유 예산과 실제 제공 엔드포인트 동작을 별도 시험해야 한다.

Dense와 MoE의 전체 파라미터 수만 비교해 성능이 같다고 판단하지 않는다. 활성 수 역시
정확도 점수가 아니다. 특히 총 30B / 활성 3B를 Qwen 27B Dense와 같은 계산량으로 보면 안 된다.
제공자의 실제 가중치 리비전·양자화·서빙 설정은 이 목록으로 확인할 수 없다.

## 다른 무료 모델

MiMo-V2.6-Flash Free와 DeepSeek V4.1 Flash Free는 현재 목록에서 추론·도구 호출과 이미지
입력을 지원하며 컨텍스트 200,000 / 출력 32,000으로 표시됐다. 더 큰 MoE 계열이므로
사내 모델의 크기를 재현하는 후보보다 다른 모델에서의 실패를 찾는 비교군으로 본다.
개발사 원래 모델의 1M 컨텍스트를 OpenCode 제공 한도로 그대로 적지 않는다.

Beam Free와 Big Pickle은 여기서 활용할 공개 구조·활성 파라미터 근거가 충분하지 않아
사양 유사성 기준의 우선 후보에서 제외했다. Nemotron Ultra/Super VL도 별도 대형 비교군으로
두고, 이름에 포함된 숫자나 마케팅 등급만으로 27B 유사 모델로 분류하지 않는다.

## QA에 적용할 판단

- **256K 컨텍스트·텍스트 작업 절차 재현 후보:** Flint와 Nemotron Lightning.
- **이미지로 렌더링한 규격표·다른 모델 비교군:** GLM Flash. 현재 목록에서 PDF 직접 입력은
  세 후보 모두 false이므로, PDF를 로컬에서 텍스트 또는 페이지 이미지로 추출해야 한다.
- Nemotron 개발사 권장 언어 목록에는 한국어가 명시되지 않았다. 한국어 명세·질문을 잘
  처리한다고 가정하지 말고 합성 한국어 fixture로 확인한다.
- 후보의 한국어 이해, 필드 누락, 길이 계산, enum/Bits, 검증 피드백 수정, 불명확 정보의
  추측 방지를 같은 문제로 측정한다. 성능 우열이나 동급 여부는 이 조사만으로 확정하지 않는다.
- 후보별 원본→IR→XML→Core 검증을 새 세션에서 반복하고 모든 결과를 남긴다. 더 강한 모델의
  통과만으로 사내 모델의 통과를 예측하지 않는다.

## 무료 이용 조건

OpenCode 공식 문서의 무료 제공은 기간 한정이다. 실제 호출 가능 여부·사용 제한은 실행할 때
확인한다. 무료 chat 모델은 OpenCode 내부에서만 제공되며, 다른 클라이언트에서 직접 API로
사용하면 403을 반환한다고 명시되어 있다. Claude/Bifrost에 무료 API를 붙이는 방식으로
우회하지 않는다. OpenCode 자체의 Skill 실행 QA로 결과를 기록한다.

일부 무료 모델은 데이터 보관·개선 목적 이용 조건이 있다. Flint는 무료 기간 데이터 개선
이용과 30일 보관, NVIDIA 무료 엔드포인트는 시험용·개인정보/기밀정보 제출 금지 및 로그
이용을 명시한다. 실제 사내 ICD·소스·패킷 대신 독립적인 합성 자료만 사용한다.

## 근거

- [OpenCode 모델·무료 조건·프라이버시](https://opencode.ai/v2/docs/console/models/)
- [OpenCode 무료 모델의 외부 클라이언트 제한](https://opencode.ai/v2/docs/console/api/inference/)
- [Qwen3.6-27B 개발사 카드](https://huggingface.co/Qwen/Qwen3.6-27B)
- [Flint 개발사 카드](https://huggingface.co/RecursiveSI/flint)
- [Nemotron Lightning 개발사 사양·언어](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)
- [Nemotron Lightning NIM 가이드](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3.5-lightning.html)
- [GLM Flash 구조 확인](https://docs.nvidia.com/nemo/automodel/latest/model-coverage/vision-language-models/thudm/GLM-5.3-Flash)
- [DeepSeek V4.1 Flash 개발사 설명](https://deepseek.com/en/news/deepseek-v4-1-flash/)
