# AX Eval

Added an [AGENTS.md](https://github.com/todogroup/todogroup.org/blob/main/AGENTS.md) to the [todogroup.org](https://todogroup.org) site's repo. [AGENTS.md](https://agents.md) is an open format, part of the Agentic AI Foundation, that tells coding agents how a project works: how to run it, where files go and which rules to follow.

This repo has the eval used to measure what that AGENTS.md is worth. It runs the same tasks on two copies of the [todogroup.org repo](https://github.com/todogroup/todogroup.org): one with AGENTS.md and one without. With AGENTS.md, the agent did the task fully right in 9 of 9 runs instead of 7 of 9. It also made 34% fewer tool calls, used 36% fewer tokens, took 32% less time and cost 26% less.

You can use this repo to:

- see how each number was measured
- run the same eval again with another agent or model
- copy the method to test whether your own project's site and docs are agent-ready

This eval follows the [Agent Experience Practitioner Playbook](https://github.com/microsoft/scope/blob/main/docs/ax-playbook/ax-playbook.pdf).
The playbook explains how to test whether agents can use your product, and how to measure if a change makes it better.

## Results

Claude Code 2.1.303 with Opus 5.5, 5 November 2026. Three tasks, three runs each, on each copy (18 runs).

| Task | Condition | Runs | All criteria passed | Criteria passed | Tool calls | Tokens | Time (s) | Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1_run_locally | with | 3 | 3/3 | 100% | 7.7 | 258,456 | 41 | 0.27 |
| t1_run_locally | without | 3 | 3/3 | 100% | 10.3 | 367,082 | 59 | 0.36 |
| t2_add_blog_post | with | 3 | 3/3 | 100% | 13.0 | 422,863 | 65 | 0.34 |
| t2_add_blog_post | without | 3 | 2/3 | 89% | 22.0 | 717,197 | 95 | 0.47 |
| t6_blog_rules_question | with | 3 | 3/3 | 100% | 5.3 | 172,548 | 26 | 0.24 |
| t6_blog_rules_question | without | 3 | 2/3 | 92% | 7.0 | 257,528 | 41 | 0.30 |

Values are means across runs. Tokens include cached input. Cost is Claude Code's own [estimate at API list prices](https://code.claude.com/docs/en/agent-sdk/cost-tracking), not a bill. It is a small sample: read it as a direction, not a benchmark.

## What is in this folder

| File | What it is |
| --- | --- |
| `tasks.yaml` | The 6 tasks, written the way a contributor would ask, with the criteria for each |
| `criteria.yaml` | The 31 criteria. `dependsOn` makes a criterion count only when its parents pass |
| `eval.json` | Tasks, criteria and evidence checks in one file. This is what `run_eval.py` reads |
| `run_eval.py` | Runs the eval with Claude Code on your computer. Python standard library only |
| `setup-branches.sh` | Creates the two copies as branches in your fork |
| `export_results.py` | Copies the results into `results/` without local paths, ready to publish |
| `eval-cover.png` | Placeholder image used by the blog post task |
| `scope/` | Profiles and request bodies to run the same eval with [Scope](https://microsoft.github.io/scope/) |

## The tasks

| Task | What the agent must do | What it tests |
| --- | --- | --- |
| t1 | Get the site running locally | Versions, Hugo extended, the theme submodule |
| t2 | Add a blog post with an image | Blog folder, image folder, front matter |
| t3 | Add a case study | Find the section and copy its structure |
| t4 | Add a working group page | Landing page cards, no made-up links |
| t5 | Translate a guide to Japanese | Multilingual folders |
| t6 | Answer where blog posts and images go | Reading only, no file changes |

The results above use t1, t2 and t6.

## How a run works

For each task, condition and repetition, `run_eval.py`:

1. makes a fresh copy of the branch,
2. runs the task with `claude -p` (non-interactive) and records tool calls, tokens, time and cost,
3. records the evidence: changed files, the commands the agent ran and its final answer,
4. builds the site with `npm run build`,
5. asks a second Claude session, the grader, to check each criterion against the evidence,
6. applies the criteria graph: a criterion is skipped when one of its parents fails.

**Guardrails.** Each run works in its own copy, so your own checkout is never touched. The agent may use git, npm, npx, node, Hugo and basic file commands. Web search, web fetch, `sudo`, Homebrew, global npm installs and `git push` are blocked. After each run the script stops any server the agent left running. The grader runs with no tools, from an empty folder, and sees only the evidence.

## Run it

**You need:** Claude Code (logged in), Python 3, git, Node.js 22, and a fork of todogroup/todogroup.org.

1. Create the two branches in your fork:
   ```
   ./setup-branches.sh <your-github-user>
   ```
   `eval/with-agents-md` is upstream `main` plus a one-line `CLAUDE.md` (`@AGENTS.md`), so Claude Code loads AGENTS.md at the start of each session. `eval/without-agents-md` is upstream `main` without AGENTS.md.

2. Run one task once, then check that only the "with" copy loads AGENTS.md:
   ```
   python3 run_eval.py --fork-user <your-github-user> --tasks t6 --reps 1
   cd .cache/with && claude -p "Without using any tools: is the content of AGENTS.md in your context? Quote its first heading, or say NOT LOADED." ; cd ../..
   cd .cache/without && claude -p "Without using any tools: is the content of AGENTS.md in your context? Quote its first heading, or say NOT LOADED." ; cd ../..
   ```

3. Run the eval:
   ```
   python3 run_eval.py --fork-user <your-github-user>                      # t1, t2, t6 x 3 runs
   python3 run_eval.py --fork-user <your-github-user> --tasks all --reps 5 # all 6 tasks x 5 runs
   ```
   Stop it with Ctrl+C and run the same command again to continue. Runs already done are skipped.

4. Read `summary.md`, then the grader's reasons in `runs/<task>/<condition>/repN/grade.json`. **Check the grader.** If a failure looks wrong, improve the evidence checks in `eval.json` and run `python3 run_eval.py --fork-user <your-github-user> --regrade`. It re-runs only the grader, not the agents.

Useful options: `--model` and `--grader-model` set the models, `--dry-run` prints the plan, `--timeout` sets the limit per run in seconds.

## Publish your results

```
python3 export_results.py
```

It copies `summary.md`, `results.csv` and every `grade.json` into `results/`, and replaces your home folder, user name and computer name with placeholders. It does not copy transcripts or evidence files, which can contain local paths. Review `results/` before you commit it.

## Run it with Scope

The `scope/` folder has two agent profiles (GitHub Copilot CLI and Claude Code) and 24 request bodies (6 tasks x 2 codebases x 2 agents). Add the two branches as codebases with the slugs `todogroup-with-agents-md` and `todogroup-without-agents-md`, create the criteria from `criteria.yaml`, set the model in the profiles, and submit the requests.

## Limits

- One agent and one model. Results with other agents or models can differ.
- The grader is the same model as the agent, in a separate session. The criteria are specific and checked against real evidence, but read the reasons before you trust a number.
- `main` already has fixed README and CONTRIBUTING files, so this measures what AGENTS.md adds on top of good docs.
- The criteria were checked against `main` on 5 November 2026. If the site structure changes, update them.
