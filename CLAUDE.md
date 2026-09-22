# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AgentLoop is a LangGraph-orchestrated multi-agent system that drives the **Claude Code CLI** (`claude -p`) to run end-to-end dev tasks — plan → human approval → implement → review, with a review-driven retry loop — against a separate **target project** (e.g. `my-project`), not against itself. This repo has no application code of its own to build/lint/test; "the code" it operates on lives in the target project, whose stack is detected dynamically, never assumed.

See `ARCHITECTURE.md` for the full node-by-node design and `README.md` for setup/usage instructions. This file only covers what those don't: quick commands and the architectural traps that aren't obvious from filenames alone.

## Keep docs in sync with the change

This repo has no test suite to catch documentation drift, so it's happened before (e.g. `ARCHITECTURE.md` once said `docker.sock` wasn't mounted after it already had been). Whenever a change touches one of the following, update the matching doc **in the same change**, not as a follow-up:

- `nodes/*.py`, `core/*.py`, `lib/*.py` → update the relevant node/flow description in `ARCHITECTURE.md`
- `Dockerfile`, `docker-compose.yml`, `.env` → update the 容器化層/DooD section in `ARCHITECTURE.md` and the setup steps in `README.md`
- anything changing how the workflow is invoked or configured → update `README.md`'s 安裝與使用 section

If a doc claim can't be verified from the current code/config in the same glance (a mount, an env var, a command), don't assume it's still true — re-check it before relying on it or repeating it elsewhere.

## Commands

Everything runs inside the Docker container (see `README.md` for `.env` / `docker-compose.yml` setup — it requires `HOST_WORKSPACE_ROOT` and `TARGET_PROJECT` and mounts the target project by the _same absolute path_ as on the host):

```bash
docker compose build
docker compose up -d
docker exec -it agent_loop bash
```

Inside the container, working directory is `${HOST_WORKSPACE_ROOT}` (the parent of `AgentLoop/`), so it's invoked as a package:

```bash
# full workflow
python -m AgentLoop.main "task description"

# run from a specific node; lists available changes in TARGET_PROJECT/.agentloop/changes/ for selection,
# then continues the rest of the workflow (human_confirm cannot be run standalone).
# Takes NO task description — it comes from the selected change's state.json, and passing one is an
# error because it would overwrite the real task. So --node always needs an existing change state.
python -m AgentLoop.main --node analyze_plan
python -m AgentLoop.main --node execute
python -m AgentLoop.main --node review
python -m AgentLoop.main --node archive

# semantic search over TARGET_PROJECT's openspec (see search.py)
python -m AgentLoop.search "query"
python -m AgentLoop.search --reindex "query"   # force rebuild index before searching
```

Run tests inside the container from `${HOST_WORKSPACE_ROOT}`:

```bash
# unit tests (state persistence, routing logic) — fast, no Claude CLI needed
pytest AgentLoop/tests/test_state_persistence.py -v

# workflow entry point tests (LangGraph routing with mocked nodes) — no Claude CLI needed
pytest AgentLoop/tests/test_workflow_entrypoints.py -v

# all tests
pytest AgentLoop/tests/ -v
```

When editing a node, also verify its `_SYSTEM` prompt still produces output the regexes in that node (or in `workflow.py`'s routing functions) can parse.

## Architecture: what requires cross-file reading

**State flows one way through a compiled `StateGraph` (`workflow.py`), never through direct node-to-node calls.** All four nodes (`nodes/analyze_plan.py`, `human_confirm.py`, `execute.py`, `review.py`) read/write only the shared `AgentState` TypedDict (`state.py`). Two conditional-edge functions in `workflow.py` (`route_after_confirm`, `route_after_review`) are the only place routing decisions are made. `route_after_confirm` reads `status` directly. `route_after_review` reads the boolean `review_blocking` that `review_node` computes internally — it no longer parses `review_result` itself — so if you touch `review.py`'s output-format instructions, check its own `has_blocking_issues`/`extract_review_level`/`extract_suggestions` regexes there, since they're still brittle to prompt wording changes even though `workflow.py` is now insulated from them.

**`claude_runner.py` is the only place that talks to the `claude` CLI.** Every node prompt goes through `call_claude()`, which streams `stream-json` output, extracts the final `result` event, and — critically — contains a `while True` retry loop that pauses on usage-limit errors (detected by `is_usage_limit_error`) and waits for a human keypress before retrying — the retry itself resumes the same interrupted session via `--resume <session_id>` (captured from the failed attempt's stream) with a short continuation prompt, rather than resending the original prompt cold, so partial edits/checkbox state from before the interruption aren't silently redone or skipped; only falls back to a fresh prompt if no session_id was captured before the error.

`is_usage_limit_error` needs **both** of its layers: `_TOKEN_LIMIT_KEYWORDS` only covers API/billing wording, while subscription plans (Pro/Max/Team seat) print `You've hit your <session|weekly|Opus> limit · resets <time>`, which matches none of those keywords — so `_LIMIT_MESSAGE_RE` matches the sentence shape instead, minus `context limit` (waiting doesn't clear a full context window). Getting this wrong doesn't degrade into a failed retry; it makes the node return `status: "error"` outright and the rest of the workflow skip (this actually happened to `execute`). If you touch either layer, keep `tests/test_usage_limit_resume.py` passing — it pins the exact CLI strings.

**The pause loop only helps while the process is alive.** `session_id` lives in `ClaudeResult`, so once the user answers `q`, hits Ctrl-C, or a node returns error and the workflow ends, the session is unreachable unless it was persisted. The escape hatch is a **single session slot** in `AgentState` (`session_node` + `session_id`, written to `state.json`), read/written only through `core/session.py`'s `take_session()`/`store_session()` and wired into all three Claude-calling nodes (`analyze_plan`, `execute`, `review`) via `claude_runner.call_resuming()`. It's one slot rather than a node→id map because a change can only ever have one interrupted session: an interruption ends the whole workflow (`review` skips on upstream error, `route_after_review` ENDs on error), and a node clears its own slot once it reaches a verdict, so `store_session()` replaces wholesale instead of merging and can't accumulate orphaned ids. The slot still records its owner node because `--node` can enter anywhere and `execute` must never `--resume` an `analyze_plan` session (different tool preset, different work). On resume, `call_resuming()` sends only `RESUME_AFTER_INTERRUPT_PROMPT` instead of the full prompt — that distinction matters because `execute`'s `_SYSTEM` says "逐一執行每個 TASK，不跳過" with no "skip the already-checked ones" rule, so a cold full-prompt restart can redo finished work. A stale session falls back to the full prompt, but **hitting the limit again on resume does not count as stale** — otherwise the fallback would redo completed work. `call_resuming()` takes a caller-supplied `run(prompt, resume)` because each node wraps `call_claude` in its own loop (grilling + validate-fix in `analyze_plan`, report-completion retries in `review`). `--resume` is also used independently by the "grilling" question/answer loop (see below). Tool permissions are capped per node via `TOOL_PRESETS` (`readonly`/`plan`/`revise`/`full`/`check`/`review`) — this is the actual security boundary, not anything in the node prompts.

**`analyze_plan.py` has three distinct system prompts selected by which `AgentState` fields are populated**, not by an explicit mode flag: `review_result` set → replan-from-review; `human_feedback` set (and no `review_result`) → replan-from-human; neither set → initial plan. Each drives a different depth of the grilling interactive-clarification protocol (full grilling + domain-modeling for initial/human-revise, review-issues-only for replan) via `_run_with_grilling()`, which loops on a `QUESTION:`-prefixed response and resumes the same Claude session with the user's answer — don't confuse this with `human_confirm`, which is a separate, non-resumable y/N gate after planning completes.

**Code review happens exactly once, in `review`, by design — `execute` deliberately does not review its own work.** `execute.py`'s `_SYSTEM` forbids commit and `/code-review` so that `review_node`'s two-axis Standards/Spec review (via the `code-review` skill's parallel sub-agents, requiring the `Task` tool) is the only review pass. If you're touching either prompt, preserve this split — reintroducing self-review in `execute` would silently duplicate the review pass. `execute` and `review` both read the OpenSpec change folder themselves (not a flattened `state["plan"]` copy); `review` additionally re-derives `git diff HEAD` and does not receive `execution_result`. Both nodes independently run the target project's test suite (execute to auto-fix failures, review to verify without trusting execute's self-report) — this duplication _is_ intentional.

**`review` can finish without calling Claude at all.** `_run_spec_trace_check()` greps the target project for a `describe`/`test` named exactly like each `#### Scenario:` in the change's specs, *before* the Claude call. Any Scenario without one short-circuits the node to `review_blocking: True` / `review_level: "修補"` and straight back to replan, spending no review tokens; otherwise the per-Scenario result is injected as `<<SPEC_TRACE_RESULT>>` and the prompt is told to quote it rather than grep again. This was an instruction in `_SYSTEM` before, and as an instruction it got skipped — a Scenario with no test could still come back `Ready to merge? Yes`. So if you are debugging "review came back 修補 with only a `## Spec` section and no Standards axis", that is the short-circuit, not a truncated report — look at the trace check before the prompt. The `_SYSTEM` rule that a missing test forces `No` is now near-unreachable belt-and-braces and should stay that way.

**No target project's structure is ever hardcoded.** `project_context.py` scans the workspace root for `CLAUDE.md`/`AGENT.md`/`AGENTS.md` per subdirectory and injects a hint block (not the file contents) into every node's prompt; the agent decides at runtime which project docs to `Read`. `skill_loader.py` similarly injects Claude Code skills from `AgentLoop/.claude/skills/` (fallback `~/.claude/skills/`) — the whitelist `_FULL_CONTENT_SKILLS` (`grilling`, `domain-modeling`, `code-review`, `tdd`, `openspec-authoring`) gets full content injected; everything else is listed by name only, left for the agent to pick based on the detected stack. Name-only listing only works if Claude Code's own native skill discovery happens to find a same-named skill — verified empirically that this discovery is keyed off the invoking user's `$HOME/.claude/skills/`, not the `cwd` `claude_runner.py` passes to the subprocess, so a project-bundled skill under `AgentLoop/.claude/skills/` is never found by it. `tdd` was moved into the whitelist for exactly this reason (it needs to work regardless of whose machine runs the container), and `openspec-authoring` exists only under `AgentLoop/.claude/skills/`, so name-only listing would never resolve it at all.

**The filesystem is shared memory across iterations.** Specs live in the target project's `<project_dir>/openspec/changes/<change_name>/` (`proposal.md` / `tasks.md` / `specs/**/*.md`, plus `design.md` when needed), written by `analyze_plan` and read by `human_confirm` (via `_read_change_artifacts`), `execute`, `review`, and `archive`. The git **branch name** is asked once at the terminal (`_ask_branch_name()`, not through Claude) on the first initial-planning call — it is required and cannot be blank — and persisted in `AgentState["branch_name"]`. `change_name` is the kebab-case form of that branch. `git_ops.ensure_on_branch()` checks out (or creates) that branch in the target project before planning writes, execute, review, and archive. Review reports land in `docs/nodes/review/YYYY-MM-DD-iterN.md`. When debugging why a node picked up (or missed) prior context, check the OpenSpec change directory before assuming it's a prompt bug.

**The spec format lives in `.claude/skills/openspec-authoring/SKILL.md`, not in node code and not in a `to-spec` / `_SPEC_TEMPLATE` document.** It used to be three module constants in `nodes/analyze_plan.py` (`_OPENSPEC_ARTIFACT_RULES` / `_SPECINE_ALIGNMENT` / `_OPENSPEC_TEMPLATES`) interpolated into the `_SYSTEM` strings; edit the skill file instead, and note that `tests/evals/` pins its behaviour by feeding that same file to the CLI as a system prompt. One optimisation was lost in the move: the skeleton templates used to be injected for initial planning only, but they now share the file with the rules and `openspec-authoring` is listed in both `_SKILLS` and `_SKILLS_REPLAN`, so replan pays for them too — splitting the templates into their own `_SKILLS`-only skill would win it back.

`project_dir`/`change_name` are resolved by Python before the Claude call (not reported back by Claude), so chat output from `analyze_plan` carries no output contract at all — just a one-line completion status; it must not repeat analysis/plan summaries. `execute` and `review` are given the change path and Read the files; they do not receive a flattened TASK list in the prompt. Specine's ten alignment ingredients are mapped into OpenSpec fields; grilling (initial plan) must leave three mandatory ones in the artifacts — specification purpose (`proposal.md` Intent), output requirements (Requirement + Scenario THEN), and examples with explanations (at least one main-path Scenario with step-by-step input-to-output logic) — the other seven are included only when they apply. Do not add a separate Specine chapter. Two rules in there are load-bearing for other nodes and easy to break by "tidying": a spec states only what the system guarantees (never a `MUST NOT` or a negative Scenario for an absent feature, and nothing at all about code that was never specced), and `tasks.md` must spell out test-deletion tasks by Scenario title, because `execute` locates the tests to delete from those titles and leftovers then skew `review`'s trace check.

**Containerization is Docker-outside-of-Docker, not Docker-in-Docker.** The container has no daemon; it mounts the host's `/var/run/docker.sock` and runs `sudo docker ...` (passwordless, restricted to `/usr/bin/docker` for the non-root `agent` user) against the host engine. This is why `AgentLoop` and the target project are bind-mounted at the _same absolute path_ inside the container as on the host (`${HOST_WORKSPACE_ROOT}/...`) rather than remapped to `/workspace/...`: the host daemon resolves bind-mount paths as literal strings, and a remapped path wouldn't exist on the host.

**The container's Claude Code login is deliberately isolated from the host's, on a named volume (`agent_home:/home/agent`).** Don't "fix" this back to bind-mounting the host's `~/.claude` — that was the original design and it caused real, hard-to-diagnose failures: host and container `claude` processes sharing one OAuth credential file race on token refresh, which surfaces as a node erroring mid-run (auth suddenly invalid) or as "not logged in" right at startup (credential file caught mid-write). Only `~/.claude/skills` and `~/.agents` are still bind-mounted from the host, and only read-only, because skill content is static and never written to at runtime. First-time container setup needs its own `claude login` (or `ANTHROPIC_API_KEY`) inside the container — see `README.md`.
