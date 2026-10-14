# CLAUDE.md

This file tells an agent editing this repo where the documentation lives. Do not restate those documents here; read the one that owns the topic and treat it as the source.

## Where to look

- **What this is, setup, commands, web console, container login, usage-limit pause, search** — `README.md`, from 安裝與使用 onward.
- **How the workflow actually works** — `ARCHITECTURE.md`. Use its headings; the behavior is specified there, not here:
  - state, graph, routing — 核心資料結構、工作流程
  - `analyze_plan` modes (initial / human-revise / replan / adjustment), branch, domain, `skip_specs`, grilling — 1. `analyze_plan`
  - `execute` / `review` split, spec-trace short-circuit — 3. `execute`、4. `review`
  - every user question goes through `lib/interaction.py` — 互動埠
  - `stages` is written only by `_tracked()` / `start()` / `finish()` — 階段狀態
  - `claude_runner`, usage-limit detection, session slot, `LANGUAGE_POLICY`, `TOOL_PRESETS` — Claude Runner。改用量上限判定時讓 `tests/test_usage_limit_resume.py` 維持通過
  - skill injection, and why a name-only skill is not discovered from this repo — Skill 系統作為知識注入
  - OpenSpec change folder as shared memory — 檔案系統作為共享記憶
  - spec format — `.claude/skills/openspec-authoring/SKILL.md`（`ARCHITECTURE.md` 的 analyze_plan 只做導覽）
  - Docker outside of Docker and `agent_home` — 容器化層；第一次登入步驟在 `README.md`
- **Domain vocabulary**（任務、調整、審查退回、…）— `CONTEXT.md`

Tests are not listed in `README.md`. From `${HOST_WORKSPACE_ROOT}` inside the container:

```bash
pytest AgentLoop/tests/ -v
cd AgentLoop/web/frontend && npx vitest run   # npm install once first
```

When editing a node's `_SYSTEM`, confirm the output still matches the regexes in that node. `route_after_review` reads `review_blocking`, not the report text.

## Keep docs in sync with the change

This repo has no test suite to catch documentation drift, so it's happened before (e.g. `ARCHITECTURE.md` once said `docker.sock` wasn't mounted after it already had been). Whenever a change touches one of the following, update the matching doc **in the same change**, not as a follow-up:

- `nodes/*.py`, `core/*.py`, `lib/*.py` → update the relevant node/flow description in `ARCHITECTURE.md`
- `Dockerfile`, `docker-compose.yml`, `.env` → update the 容器化層/DooD section in `ARCHITECTURE.md` and the setup steps in `README.md`
- anything changing how the workflow is invoked or configured → update `README.md`'s 安裝與使用 section

If a doc claim can't be verified from the current code/config in the same glance (a mount, an env var, a command), don't assume it's still true — re-check it before relying on it or repeating it elsewhere.

## Keep prompts from growing

Every prompt edit — a node's `_SYSTEM` / continuation prompt, or a skill whose full text is injected into one (`openspec-authoring`, `grilling`, `tdd`, `domain-modeling`, `code-review`) — has to leave the prompt shorter or the same length in substance, not longer by default. Input tokens are the bill, and restated rules get ignored once the prompt is long enough.

Before adding or rewording a sentence, read the prompt you are about to change **and** the other text that will sit in the same Claude call:

- that node's other `_SYSTEM` variants (analyze_plan's initial / replan / human-revise already share blocks; a rule added to one usually belongs in the shared block or in none of them)
- every full-content skill that call injects — if the skill already states the rule, the node prompt must not state it again. Pass only what the skill cannot know (this run's path, branch, change name, the user's decision such as `skip_specs: true|false` or a domain name). A pointer ("見 OpenSpec 產出規則") is fine; a paraphrase of the skill is not
- the other nodes' prompts, so the same instruction is not copied into `execute` and `review` independently

Delete or merge the overlap in the same change. Do not append a new section to "make sure the model sees it" when an existing sentence or the injected skill already covers it.
