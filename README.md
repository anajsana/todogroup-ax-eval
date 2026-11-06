# AX Eval

Added an [AGENTS.md](https://github.com/todogroup/todogroup.org/blob/main/AGENTS.md) to the [todogroup.org](https://todogroup.org) site's repo. [AGENTS.md](https://agents.md) is an open format, part of the Agentic AI Foundation, that tells coding agents how a project works: how to run it, where files go and which rules to follow.

This repo has the eval used to measure what that AGENTS.md is worth. It runs the same tasks on two copies of the [todogroup.org repo](https://github.com/todogroup/todogroup.org): one with AGENTS.md and one without. With AGENTS.md, the agent did the task fully right in 9 of 9 runs instead of 7 of 9. It also made 34% fewer tool calls, used 36% fewer tokens, took 32% less time and cost 26% less.

You can use this repo to:

- see how each number was measured
- run the same eval again with another agent or model
- copy the method to test whether your own project's site and docs are agent-ready

This eval follows the [Agent Experience Practitioner Playbook](https://github.com/microsoft/scope/blob/main/docs/ax-playbook/ax-playbook.pdf).
The playbook explains how to test whether agents can use your product, and how to measure if a change makes it better.
