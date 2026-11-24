# AGENTS.md

Read this whole file before doing anything. It applies to every agent and tool (Claude Code, Codex, Cursor, Copilot, Antigravity, subagents). `CLAUDE.md` just points here.

## Project in one paragraph

**VIA (Variant Interpretation Agent)** is a portfolio project: a tool-using LLM agent that takes one human DNA variant (chromosome, position, ref, alt on GRCh38) and writes a structured, cited report saying whether it is likely pathogenic, likely benign, or uncertain. It gathers evidence from free public sources (Ensembl VEP, gnomAD, AlphaMissense, UniProt, AlphaFold DB) and every claim in the report must point to a tool result. The half that matters most is the evaluation: about 200 ClinVar variants with ≥ 3-star review (expert panel or practice guideline), with ClinVar hidden from the agent during evaluation, compared against simple baselines (gnomAD-only rule, AlphaMissense alone, the LLM with no tools) and reporting accuracy together with how often the agent abstains. It is not a clinical tool and gives no medical advice. Plan: `PLAN.md`. Design: `ARCHITECTURE.md`. Session log: `docs/devlog.md`.

## 1. Workflow rules (always)

### W1. Work is a FIFO queue
- Keep every request as a todo in a queue, in arrival order.
- New requests, tweaks and corrections from the user go to the back of the queue. Do not drop the current item to jump to the new one.
- Exception: the user explicitly says "stop", "now", or "first", or the new message makes the current item wrong (e.g. "don't touch that file"). Then reorder and say so.
- Stop only when every item is in a final state: **done**, **skipped** (with why), or **blocked** (with what it waits on). Before ending, list the queue with each item's final state.

### W2. Read everything first, then edit, then test once
1. List every file you need for the task.
2. Read them all in one pass (parallel reads).
3. Make all edits.
4. Run the tests/checks once at the end. Re-run only what you fix.

Why: interleaving read→edit→test burns context and leaves files in half-edited states.

### W3. YAGNI: build only what the current milestone needs
- Build the smallest thing that meets the current milestone in `PLAN.md` §4.
- No new abstraction, dependency, config option or file unless the current task needs it now.
- Anything in `PLAN.md` §3.2 (out of scope) needs an explicit user request.

### W4. Suggest scope improvements, briefly and with a reason
At the end of a task, propose up to 3 scope improvements (additions or cuts). Each must say why, with evidence (a risk ID from `PLAN.md` §5, a metric, a bug seen), and roughly how big it is. Do not build them unless asked.

### W5. Fresh-eyes review by a cheap subagent
The user authorises this standing rule. After any change that touches code, the evaluation protocol, or more than one doc, start a subagent with the cheapest available model (e.g. Haiku) and minimal context: give it only the diff (`git diff` or the changed files), this `AGENTS.md`, and one line of intent. Ask it to list concrete problems (bugs, contradictions, rule violations, missing tests, **evaluation leakage**) and not to edit files. Then fix or explicitly reject each finding, with a reason. The reviewer does not apply W5 to itself (no recursive reviews). Skip for typo-level edits.

### W6. Let the user grill the plan
For design or planning work, offer to run the `grilling` skill (or ask a short set of hard questions yourself) so the user can stress-test the decision before it is built. Before offering any option, check it against the actual mechanism (the real API response, the real file, the real data licence). Do not offer options you have not verified can work.

### W7. Mistakes: no apologies, find the cause in the instructions
- Do not apologise. Apologies don't fix anything.
- When something goes wrong, state: (1) what happened, (2) which instruction was missing, unclear or conflicting (in this file, `PLAN.md`, `ARCHITECTURE.md`, or the prompt), (3) the exact fix to that instruction, written as a diff or a new rule.
- Then fix the work itself.
- Never claim a file, test or result exists unless you created or ran it in this session and saw the output.

### W8. Explain before, walk through after
The owner doesn't write the code, but must be able to explain the app (in an interview, line by line if asked).
- **Before a milestone:** a short plain-language plan (what, why, how it will be checked), and wait for a go.
- **After a milestone:** a short walkthrough of what was built and how to run it. Explain new biology or ML terms in one sentence each.
- **End of every session:** add an entry to `docs/devlog.md` (date, what was done, where it stopped, next step) so work can resume after a long break.

## 2. Git rules

- **G1. Atomic commits.** Each commit does one thing and leaves the repo working. Split unrelated docs, refactors and features into separate commits. Exception: a code change and the doc update it requires go in the same commit.
- **G2. Conventional Commits.** `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, with an optional scope, e.g. `feat(tools): add gnomAD frequency lookup`, `test(eval): add leakage guard test`.
- **G3. No bulky files.** Never commit data downloads (ClinVar/AlphaMissense TSVs, VCFs, `.gz`, parquet), HTTP caches, eval run outputs, model weights, notebooks with large outputs, archives, or any single file > 1 MB without asking. Small hand-made test fixtures (< 100 KB) in `tests/fixtures/` are fine. Check `git status` and `.gitignore` before every commit.
- **G4. No secrets.** No API keys or `.env`. Use `.env.example` with placeholder values.
- **G5. Never push on your own.** `git push` (and force-push, tags, releases) only when the user asks in the current conversation. Committing locally is fine.
- **G6. Commit only after green checks.** Run `git commit` only in a command that stops on failure (`set -e`, or `&&` after the check). Never chain a commit after `;`, where it runs even if the tests or the edit before it failed.

## 3. Project rules

- **P1. No evaluation leakage.** In eval mode the agent must not see the ClinVar record of the variant under test, by any route (ClinVar tool, VEP `colocated_variants` clinical significance fields, cached responses, prompts). Any change touching tools or eval needs a test proving this.
- **P2. Every claim is grounded.** Report evidence items must cite a tool call ID that exists in the run trace. Ungrounded claims fail validation.
- **P3. Offline tests.** `pytest` must pass with no network and no API key, using recorded fixtures. Live calls only in scripts marked as such.
- **P4. Reproducible.** Fixed random seeds, pinned dependency versions, and the model ID recorded in every eval result.
- **P5. Docs follow code.** If a change alters behaviour described in `ARCHITECTURE.md`, `PLAN.md` or `README.md`, update the doc in the same commit.
- **P6. Respect data terms.** Check a source's licence before using it; note it in `ARCHITECTURE.md` §Data sources. Use polite rate limits and caching for public APIs.
