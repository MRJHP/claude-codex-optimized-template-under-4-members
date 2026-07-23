---
name: startproject
description: 멀티 에이전트 협력(Claude 계획 + Codex 리뷰)으로 새 프로젝트/기능을 시작한다. "새 프로젝트 시작해줘", "이 기능 처음부터 설계해줘" 같은 요청에 사용한다.
---

# startproject

새 프로젝트 또는 새 기능을 시작할 때 Claude와 Codex의 역할을 분담해서 진행하는 절차.

## 절차

1. **요구사항 파악**: 사용자에게 목표, 제약(기한, 기술 스택, 기존 시스템과의 연동)을 명확히 한다. 애매하면
   AskUserQuestion으로 확인한다.
2. **템플릿 커스터마이즈** (완전히 새 프로젝트인 경우): [init 스킬](../init/SKILL.md)로 이 템플릿을 실제
   프로젝트에 맞게 초기화한다 (README, `src/`·`tests/` 구조, `pyproject.toml` 프로젝트명 등).
3. **설계 초안 작성**: [.claude/docs/DESIGN.md](../../docs/DESIGN.md)에 개요와 핵심 아키텍처 결정 초안을 작성한다.
4. **Codex 세컨드 오피니언** (아키텍처가 자명하지 않은 경우): `mcp__codex__codex`로 설계 초안을 공유하고
   놓친 리스크나 대안이 있는지 물어본다. [codex-delegation.md](../../rules/codex-delegation.md) 기준 참고.
5. **구현 계획 작성**: [plan 스킬](../plan/SKILL.md)로 단계별 구현 계획을 세운다.
6. **TDD로 구현 시작**: [tdd 스킬](../tdd/SKILL.md) 절차를 따른다.

## 체크리스트

- [ ] 요구사항이 사용자와 합의됨
- [ ] DESIGN.md에 개요가 기록됨
- [ ] 애매한 아키텍처 결정에 대해 Codex 의견을 구했음 (해당 시)
- [ ] 구현 계획이 사용자 승인을 받음
- [ ] 첫 테스트가 작성됨
