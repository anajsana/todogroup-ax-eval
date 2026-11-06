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

| Task | Condition | Runs | All criteria passed | Criteria passed | Tool calls | Tokens | Time (s) | Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1_run_locally | with | 3 | 3/3 | 100% | 7.7 | 258,456 | 41 | 0.27 |
| t1_run_locally | without | 3 | 3/3 | 100% | 10.3 | 367,082 | 59 | 0.36 |
| t2_add_blog_post | with | 3 | 3/3 | 100% | 13.0 | 422,863 | 65 | 0.34 |
| t2_add_blog_post | without | 3 | 2/3 | 89% | 22.0 | 717,197 | 95 | 0.47 |
| t6_blog_rules_question | with | 3 | 3/3 | 100% | 5.3 | 172,548 | 26 | 0.24 |
| t6_blog_rules_question | without | 3 | 2/3 | 92% | 7.0 | 257,528 | 41 | 0.30 |

## Folder architecture

| File | What it is |
| --- | --- |
| `tasks.yaml` | The 6 tasks, written the way a contributor would ask, with the criteria for each |
| `criteria.yaml` | The 31 criteria|
| `eval.json` | Tasks, criteria and evidence checks in one file|
| `run_eval.py` | Runs the eval with Claude code on your computer|
| `setup-branches.sh` | Creates the two copies as branches in your fork |
| `export_results.py` | Copies the results into `results/` without local paths, ready to publish |
| `eval-cover.png` | Placeholder image used by the blog post task |
| `scope/` | Profiles and request bodies to run the same eval with [Scope](https://microsoft.github.io/scope/) |

## Tasks

| Task | What the agent must do | What it tests |
| --- | --- | --- |
| t1 | Get the site running locally | Versions, Hugo extended, the theme submodule |
| t2 | Add a blog post with an image | Blog folder, image folder, front matter |
| t3 | Add a case study | Find the section and copy its structure |
| t4 | Add a working group page | Landing page cards, no made-up links |
| t5 | Translate a guide to Japanese | Multilingual folders |
| t6 | Answer where blog posts and images go | Reading only, no file changes |
