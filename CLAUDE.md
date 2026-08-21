# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AgentLoop is a LangGraph-orchestrated multi-agent system that drives the **Claude Code CLI** (`claude -p`) to run end-to-end dev tasks — plan → human approval → implement → review, with a review-driven retry loop — against a separate **target project** (e.g. `my-project`), not against itself. This repo has no application code of its own to build/lint/test; "the code" it operates on lives in the target project, whose stack is detected dynamically, never assumed.

See `ARCHITECTURE.md` for the full node-by-node design and `README.md` for setup/usage instructions. This file only covers what those don't: quick commands and the architectural traps that aren't obvious from filenames alone.

## Keep docs in sync with the change

This repo has no test suite to catch documentation drift, so it's happened before (e.g. `ARCHITECTURE.md` once said `docker.sock` wasn't mounted after it already had been). Whenever a change touches one of the following, update the matching doc **in the same change**, not as a follow-up:

- `nodes/*.py`, `workflow.py`, `state.py`, `claude_runner.py` → update the relevant node/flow description in `ARCHITECTURE.md`
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

# run a single node in isolation (human_confirm cannot be run standalone)
python -m AgentLoop.main --node analyze_plan "task description"
python -m AgentLoop.main --node execute --state-file /tmp/state.json "task description"
python -m AgentLoop.main --node review "task description"
```

`--state-file` preloads `AgentState` fields (e.g. `plan`, `execution_result`) from a JSON file so you can debug one node without re-running the ones before it.

There is no test/lint/build step for this repo itself — the only thing to verify when editing a node is that its `_SYSTEM` prompt still produces output the regexes in that node (or in `workflow.py`'s routing functions) can parse.

## Architecture: what requires cross-file reading

**State flows one way through a compiled `StateGraph` (`workflow.py`), never through direct node-to-node calls.** All four nodes (`nodes/analyze_plan.py`, `human_confirm.py`, `execute.py`, `review.py`) read/write only the shared `AgentState` TypedDict (`state.py`). Two conditional-edge functions in `workflow.py` (`route_after_confirm`, `route_after_review`) are the only place routing decisions are made. `route_after_confirm` reads `status` directly. `route_after_review` reads the boolean `review_blocking` that `review_node` computes internally — it no longer parses `review_result` itself — so if you touch `review.py`'s output-format instructions, check its own `has_blocking_issues`/`extract_review_level`/`extract_suggestions` regexes there, since they're still brittle to prompt wording changes even though `workflow.py` is now insulated from them.

**`claude_runner.py` is the only place that talks to the `claude` CLI.** Every node prompt goes through `call_claude()`, which streams `stream-json` output, extracts the final `result` event, and — critically — contains a `while True` retry loop that pauses on rate-limit/quota errors (detected via keyword matching in `_is_token_limit_error`) and waits for a human keypress before retrying. It also supports `--resume <session_id>` for the "grilling" question/answer loop (see below). Tool permissions are capped per node via `TOOL_PRESETS` (`readonly`/`plan`/`full`/`check`/`review`) — this is the actual security boundary, not anything in the node prompts.

**`analyze_plan.py` has three distinct system prompts selected by which `AgentState` fields are populated**, not by an explicit mode flag: `review_result` set → replan-from-review; `human_feedback` set (and no `review_result`) → replan-from-human; neither set → initial plan. Each drives a different depth of the grilling interactive-clarification protocol (full grilling + domain-modeling for initial/human-revise, review-issues-only for replan) via `_run_with_grilling()`, which loops on a `QUESTION:`-prefixed response and resumes the same Claude session with the user's answer — don't confuse this with `human_confirm`, which is a separate, non-resumable y/N gate after planning completes.

**Code review happens exactly once, in `review`, by design — `execute` deliberately does not review its own work.** `execute.py`'s `_SYSTEM` forbids commit and `/code-review` so that `review_node`'s two-axis Standards/Spec review (via the `code-review` skill's parallel sub-agents, requiring the `Task` tool) is the only review pass. If you're touching either prompt, preserve this split — reintroducing self-review in `execute` would silently duplicate the review pass. `execute` and `review` both read the OpenSpec change folder themselves (not a flattened `state["plan"]` copy); `review` additionally re-derives `git diff HEAD` and does not receive `execution_result`. Both nodes independently run the target project's test suite (execute to auto-fix failures, review to verify without trusting execute's self-report) — this duplication _is_ intentional.

**No target project's structure is ever hardcoded.** `project_context.py` scans the workspace root for `CLAUDE.md`/`AGENT.md`/`AGENTS.md` per subdirectory and injects a hint block (not the file contents) into every node's prompt; the agent decides at runtime which project docs to `Read`. `skill_loader.py` similarly injects Claude Code skills from `AgentLoop/.claude/skills/` (fallback `~/.claude/skills/`) — the whitelist `_FULL_CONTENT_SKILLS` (`grilling`, `domain-modeling`, `code-review`) gets full content injected; everything else is listed by name only, left for the agent to pick based on the detected stack.

**The filesystem is shared memory across iterations.** Specs live in the target project's `<project_dir>/openspec/changes/<change_name>/` (`proposal.md` / `tasks.md` / `specs/**/*.md`, plus `design.md` when needed), written by `analyze_plan` and read by `human_confirm` (via `_read_change_artifacts`), `execute`, `review`, and `archive`. The git **branch name** is asked once at the terminal (`_ask_branch_name()`, not through Claude) on the first initial-planning call — it is required and cannot be blank — and persisted in `AgentState["branch_name"]`. `change_name` is the kebab-case form of that branch. `git_ops.ensure_on_branch()` checks out (or creates) that branch in the target project before planning writes, execute, review, and archive. Review reports land in `docs/nodes/review/YYYY-MM-DD-iterN.md`. When debugging why a node picked up (or missed) prior context, check the OpenSpec change directory before assuming it's a prompt bug.

**The spec format is `_OPENSPEC_ARTIFACT_RULES` in `nodes/analyze_plan.py`, not a `to-spec` / `_SPEC_TEMPLATE` document.** Chat output from `analyze_plan` must not repeat analysis/plan summaries — only `PROJECT_DIR:` / `CHANGE_NAME:` (initial) or a validate confirmation (replan / human-revise). `execute` and `review` are given the change path and Read the files; they do not receive a flattened TASK list in the prompt.

**Containerization is Docker-outside-of-Docker, not Docker-in-Docker.** The container has no daemon; it mounts the host's `/var/run/docker.sock` and runs `sudo docker ...` (passwordless, restricted to `/usr/bin/docker` for the non-root `agent` user) against the host engine. This is why `AgentLoop` and the target project are bind-mounted at the _same absolute path_ inside the container as on the host (`${HOST_WORKSPACE_ROOT}/...`) rather than remapped to `/workspace/...`: the host daemon resolves bind-mount paths as literal strings, and a remapped path wouldn't exist on the host.

**The container's Claude Code login is deliberately isolated from the host's, on a named volume (`agent_home:/home/agent`).** Don't "fix" this back to bind-mounting the host's `~/.claude` — that was the original design and it caused real, hard-to-diagnose failures: host and container `claude` processes sharing one OAuth credential file race on token refresh, which surfaces as a node erroring mid-run (auth suddenly invalid) or as "not logged in" right at startup (credential file caught mid-write). Only `~/.claude/skills` and `~/.agents` are still bind-mounted from the host, and only read-only, because skill content is static and never written to at runtime. First-time container setup needs its own `claude login` (or `ANTHROPIC_API_KEY`) inside the container — see `README.md`.
