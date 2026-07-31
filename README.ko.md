# opus-5-router

[README.md](README.md)

**Opus 5 세션을 순수 오케스트레이터로** 돌린다 — 사고·분해·위임·리뷰만 하고 직접 수정은 절대 하지 않는다. Opus 5의 직접 코딩은 아쉽지만 오케스트레이션은 쓸 만할 때, 그리고 Fable 5를 판단이 필요한 곳에만 쓰고 싶을 때를 위한 플러그인.

자매 프로젝트: [fable-router](https://github.com/KyongSik-Yoon/fable-router) 플러그인은 반대 접근이다 — Fable 5가 부모로서 위임 가능한 단계를 저렴한 모델에 내려보낸다. 이 플러그인에 함께 들어 있던 그 스킬은 이제 해당 저장소에서만 유지된다.

## 동작 방식

강제는 프롬프트가 아니라 메커니즘이다. 플래그 파일 `~/.claude/opus-orchestrator`가 존재하는 동안 플러그인의 `PreToolUse` 훅(`hooks/orchestrator-guard.sh`)이 **메인 에이전트의** `Write`/`Edit`/`NotebookEdit`와, 읽기 전용 조회·테스트/린트 명령을 벗어나는 모든 Bash를 거부한다(`hooks/orchestrator-bash-filter.py`, 기본 거부). 서브에이전트 호출은 그대로 통과한다 — 훅 입력에 `agent_id`가 실려 오는 쪽이 서브에이전트고, 메인 에이전트에는 절대 없다. 거부 사유 문구가 모델을 위임 쪽으로 유도한다. `UserPromptSubmit` 훅(`hooks/orchestrator-mode.sh`)은 매 턴 오케스트레이터 태세를 주입한다.

구현은 frontmatter에 모델 ID를 핀 고정한 워커가 맡는다 — `opus` 별칭이 무엇으로 해석되든 계층이 유지된다:

| 에이전트 | 모델 | Effort | 역할 |
| --- | --- | --- | --- |
| `opus-5-router:coder-opus48` | `claude-opus-4-8` | high | 복잡한 구현, 파일 간 리팩터, 까다로운 디버깅 |
| `opus-5-router:coder-sonnet` | `claude-sonnet-5` | medium | 표준 구현, 테스트 작성, 중간 난도 수정 |
| `opus-5-router:scout` | Haiku 4.5 | low | 기계적 읽기 전용 정찰 (내장 Explore는 비싼 세션 모델을 상속받는다) |
| `opus-5-router:scout-sonnet` | `claude-sonnet-5` | low | 해석형 읽기 전용 정찰 — 모호한 코드, 흩어진 증거, 가설 수립 |
| `opus-5-router:advisor` | `fable` | high | 세션 지속형 시니어 어드바이저, 읽기 전용 |

Fable은 의무 트리거(아키텍처 결정, 티어 상승 후 2회 연속 검증 실패, 증거 충돌, 고위험 변경의 최종 리뷰)에서만 자문하며, 질문마다 새로 띄우지 않고 **하나의 지속 advisor 에이전트**를 SendMessage로 이어 쓴다. `advisor=none`으로 두면 — 예컨대 Fable 쿼터를 다 쓴 뒤 — 트리거는 대신 AskUserQuestion으로 사용자에게 간다.

## 사용법

```
/opus-orchestrator on              # advisor=fable (기본)
/opus-orchestrator on advisor=none # Fable 없는 순수 Opus 모드
/opus-orchestrator advisor none    # 모드 유지한 채 advisor만 전환
/opus-orchestrator status
/opus-orchestrator off
```

## 설치

```
/plugin marketplace add KyongSik-Yoon/opus-5-router
/plugin install opus-5-router@opus-5-router
```

모드가 실제로 뭔가를 강제하려면 플러그인 설치가 필요하다 — 훅이 플러그인과 함께 배포되기 때문. 수동 체크아웃은 `orchestrator-guard.sh`(PreToolUse, matcher `Write|Edit|NotebookEdit|Bash`)와 `orchestrator-mode.sh`(UserPromptSubmit)를 settings에 직접 연결해야 한다.

## 참고

- 스킬이 세션 모델을 바꿔줄 수는 없다. 프로젝트 `.claude/settings.json`에 `"model": "claude-opus-5"`를 넣거나 `/model`로 직접 고정할 것.
- fable-router 플러그인의 auto 모드와 동시에 켜지 말 것 — 하나는 Fable 부모, 하나는 Opus 부모를 전제한다. `/opus-orchestrator on`은 두 플래그가 겹치면 경고한다.
- Bash 필터의 목표는 우회를 어렵게 만드는 것이지 불가능하게 만드는 것이 아니다: 강제 대상은 모델 드리프트지 공격자가 아니다.
- 스카우트가 Haiku를 유지하는 이유: 정찰 비용은 input 토큰이 지배하는데 effort 설정은 input 비용을 줄여주지 못하고, Sonnet 5의 신형 토크나이저(같은 텍스트가 ~30% 더 많은 토큰)까지 겹치면 스티커 3배 가격 차가 실질 ~4배로 벌어진다(2026-08-31 종료되는 인트로 가격 기준으로도 ~2.6배). 스캔이 아니라 해석이 필요한 정찰은 Haiku의 floor를 넘으므로 `opus-5-router:scout-sonnet`으로 보낼 것.
