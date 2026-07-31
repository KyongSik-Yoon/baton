# fable-router

[README.md](README.md)

[gpt-5.6-router](https://github.com/volition79/gpt-5.6-router)에서 영감을 받아(inspired by) Claude Code용으로 이식한 스킬. Fable 5(부모)의 토큰을 아끼기 위해 위임 가능한 작업 단계를 Agent 도구의 `model` 오버라이드로 Opus/Sonnet/Haiku에 배정한다.

## 흐름

1. **Gate 1** — PERFORMANCE / BALANCED / TOKEN_SAVER 프로파일 선택 (AskUserQuestion)
2. **읽기 전용 탐색** — Haiku/Sonnet 서브에이전트로 라우팅에 필요한 최소 근거만 수집
3. **라우트 설계** — 단계별 최저 비용 모델과 안전한 최저 reasoning effort 배정, Fable-direct와 비교
4. **Gate 2** — 라우트 명시 승인 후 실행
5. **완료 보고** — 실제 라우트, 검증 결과, 편차, 잔여 리스크

## 원본 대비 변경점

- Sol/Terra/Luna → Fable/Opus·Sonnet/Haiku 역량 플로어로 재매핑
- `spawn_agent` 런타임 분류(A/B/C)·Codex 트러블슈팅 제거 — Claude Code Agent 도구는 `model` 파라미터를 항상 지원
- references/assets 문서를 SKILL.md 하나로 통합
- effort 라우팅 추가: Agent 도구에는 호출별 effort 파라미터가 없어, 플러그인이 `worker-low` / `worker-medium` / `worker-high` 에이전트 정의(`agents/`)를 제공하고 `subagent_type`으로 effort를, `model` 오버라이드로 모델을 조합해 라우팅

## 설치

### Claude Code (플러그인 마켓플레이스)

```
/plugin marketplace add KyongSik-Yoon/fable-router
/plugin install fable-router@fable-router
```

### 수동 설치

```bash
git clone https://github.com/KyongSik-Yoon/fable-router
ln -s "$(pwd)/fable-router/skills/fable-router" ~/.claude/skills/fable-router
# effort 변형 워커 에이전트 (모델 라우팅만 쓸 거면 생략 가능)
for f in fable-router/agents/*.md; do ln -s "$(pwd)/$f" ~/.claude/agents/; done
```

참고: 수동 설치 시 워커는 `fable-router:` 접두사 없이 `worker-low` 등으로 등록된다. 플러그인 설치가 문서화된 기본 경로.

### Claude Desktop / claude.ai

설정 → Capabilities → Skills에서 `skills/fable-router` 폴더(또는 zip)를 업로드.

이후 `/fable-router`로 호출. 명시 호출 시에만 활성화된다.

## Auto 모드

기본 비활성. `/fable-router auto on`이 플래그 파일 `~/.claude/fable-router-auto`를 생성하며, 존재하는 동안 프로파일·라우트 승인 질문을 건너뛰고 추천 라우트(인자에 프로파일이 없으면 BALANCED)를 즉시 실행한다. `/fable-router auto off`로 해제. 안전 불변식과 일반 권한 프롬프트는 그대로 적용된다.

플러그인으로 설치하면 매 턴 `/fable-router`를 칠 필요도 없다. 함께 배포되는 `UserPromptSubmit` 훅(`hooks/auto-route.sh`)이 같은 플래그를 확인해 각 턴에 라우팅 지시를 주입한다. 지시문에는 사소하거나 대화성 턴은 라우팅하지 말라는 조항이 들어 있다 — 그런 턴은 라우팅 오버헤드가 절약분보다 크기 때문. 플래그가 없으면 훅은 아무것도 출력하지 않고 종료한다.

수동 설치에는 훅이 붙지 않는다(스킬 심볼릭 링크만으로는 훅이 등록되지 않음). 플러그인 없이 쓰려면 `~/.claude/settings.json`의 `UserPromptSubmit` 훅이 체크아웃의 `hooks/auto-route.sh`를 가리키게 하면 된다.

## Opus orchestrator 모드

fable-router의 반전: Fable이 아래로 위임하는 대신 **Opus 5 세션이 순수 오케스트레이터**가 된다 — 사고·분해·위임·리뷰만 하고 직접 수정은 절대 하지 않는다. Opus 5의 직접 코딩은 아쉽지만 오케스트레이션은 쓸 만할 때, 그리고 Fable을 판단이 필요한 곳에만 쓰고 싶을 때를 위한 모드.

강제는 프롬프트가 아니라 메커니즘이다. 플래그 파일 `~/.claude/opus-orchestrator`가 존재하는 동안 플러그인의 `PreToolUse` 훅(`hooks/orchestrator-guard.sh`)이 **메인 에이전트의** `Write`/`Edit`/`NotebookEdit`와, 읽기 전용 조회·테스트/린트 명령을 벗어나는 모든 Bash를 거부한다(`hooks/orchestrator-bash-filter.py`, 기본 거부). 서브에이전트 호출은 그대로 통과한다 — 훅 입력에 `agent_id`가 실려 오는 쪽이 서브에이전트고, 메인 에이전트에는 절대 없다. 거부 사유 문구가 모델을 위임 쪽으로 유도한다. `UserPromptSubmit` 훅(`hooks/orchestrator-mode.sh`)은 매 턴 오케스트레이터 태세를 주입한다.

구현은 frontmatter에 모델 ID를 핀 고정한 워커가 맡는다 — `opus` 별칭이 무엇으로 해석되든 계층이 유지된다:

| 에이전트 | 모델 | Effort | 역할 |
| --- | --- | --- | --- |
| `fable-router:coder-opus48` | `claude-opus-4-8` | high | 복잡한 구현, 파일 간 리팩터, 까다로운 디버깅 |
| `fable-router:coder-sonnet` | `claude-sonnet-5` | medium | 표준 구현, 테스트 작성, 중간 난도 수정 |
| `fable-router:scout` | Haiku 4.5 | low | 읽기 전용 정찰 (내장 Explore는 비싼 세션 모델을 상속받는다) |
| `fable-router:advisor` | `fable` | high | 세션 지속형 시니어 어드바이저, 읽기 전용 |

Fable은 의무 트리거(아키텍처 결정, 티어 상승 후 2회 연속 검증 실패, 증거 충돌, 고위험 변경의 최종 리뷰)에서만 자문하며, 질문마다 새로 띄우지 않고 **하나의 지속 advisor 에이전트**를 SendMessage로 이어 쓴다. `advisor=none`으로 두면 — 예컨대 Fable 쿼터를 다 쓴 뒤 — 트리거는 대신 AskUserQuestion으로 사용자에게 간다.

```
/opus-orchestrator on              # advisor=fable (기본)
/opus-orchestrator on advisor=none # Fable 없는 순수 Opus 모드
/opus-orchestrator advisor none    # 모드 유지한 채 advisor만 전환
/opus-orchestrator status
/opus-orchestrator off
```

참고:
- 스킬이 세션 모델을 바꿔줄 수는 없다. 프로젝트 `.claude/settings.json`에 `"model": "claude-opus-5"`를 넣거나 `/model`로 직접 고정할 것.
- 플러그인 설치가 필요하다(훅). 수동 설치는 `orchestrator-guard.sh`(PreToolUse, matcher `Write|Edit|NotebookEdit|Bash`)와 `orchestrator-mode.sh`(UserPromptSubmit)를 settings에 직접 연결해야 한다.
- fable-router auto 모드와 동시에 켜지 말 것 — 하나는 Fable 부모, 하나는 Opus 부모를 전제한다. `/opus-orchestrator on`은 두 플래그가 겹치면 경고한다.
- Bash 필터의 목표는 우회를 어렵게 만드는 것이지 불가능하게 만드는 것이 아니다: 강제 대상은 모델 드리프트지 공격자가 아니다.
