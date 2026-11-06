#!/usr/bin/env python3
import argparse
import csv
import json
import os
import queue
import re
import shutil
import signal
import statistics
import threading
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONDITIONS = {"with": "eval/with-agents-md", "without": "eval/without-agents-md"}

ALLOWED_TOOLS = [
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(git:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)", "Bash(hugo:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(find:*)",
    "Bash(grep:*)", "Bash(cp:*)", "Bash(mv:*)", "Bash(mkdir:*)", "Bash(curl -s http://localhost:*)",
]
DENIED_TOOLS = [
    "WebFetch", "WebSearch",
    "Bash(sudo:*)", "Bash(brew:*)", "Bash(npm install -g:*)", "Bash(npm i -g:*)",
    "Bash(npm install --global:*)", "Bash(git push:*)",
]
CSV_FIELDS = ["task_id", "condition", "repetition", "all_passed", "criteria_passed", "criteria_total",
              "tool_calls", "num_turns", "tokens_total", "input_tokens", "output_tokens",
              "cache_read_tokens", "cache_creation_tokens", "duration_s", "cost_usd", "timed_out", "run_dir", "failed_criteria"]


def sh(cmd, cwd=None, timeout=900):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT after {timeout}s\n{e.stdout or ''}{e.stderr or ''}"


def stop_local_servers():
    sh("lsof -ti tcp:1313 | xargs kill 2>/dev/null; true")


def prepare_cache(fork_user, cache):
    cache.mkdir(parents=True, exist_ok=True)
    for cond, branch in CONDITIONS.items():
        dest = cache / cond
        if dest.exists():
            continue
        url = f"https://github.com/{fork_user}/todogroup.org.git"
        code, out = sh(f"git clone --depth 1 --branch {branch} {url} {dest}", timeout=1800)
        if code != 0:
            sys.exit(f"Could not clone {branch}:\n{out}")


def fresh_copy(cache, cond, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    code, out = sh(f"git clone --quiet --local --no-hardlinks {cache / cond} {dest}")
    if code != 0:
        sys.exit(f"Could not copy the {cond} codebase:\n{out}")


def parse_stream(lines):
    tool_calls, commands, result = 0, [], {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls += 1
                    inp = block.get("input") or {}
                    if block.get("name") == "Bash":
                        commands.append(inp.get("command", ""))
                    else:
                        target = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
                        commands.append(f"[{block.get('name')}] {target}")
        elif ev.get("type") == "result":
            result = ev
    usage = result.get("usage") or {}
    tokens = {
        "input_tokens": usage.get("input_tokens", 0) or 0,
        "output_tokens": usage.get("output_tokens", 0) or 0,
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
    }
    tokens["tokens_total"] = sum(tokens.values())
    return {
        "tool_calls": tool_calls,
        "commands": commands,
        "final_message": result.get("result", ""),
        "num_turns": result.get("num_turns", ""),
        "duration_s": round((result.get("duration_ms") or 0) / 1000, 1),
        "cost_usd": result.get("total_cost_usd", ""),
        "is_error": bool(result.get("is_error")),
        **tokens,
    }


def run_agent(repo, prompt, args, log_path):
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(args.max_turns),
           "--allowedTools", *ALLOWED_TOOLS, "--disallowedTools", *DENIED_TOOLS]
    if args.model:
        cmd += ["--model", args.model]
    stop_local_servers()
    start = time.time()
    proc = subprocess.Popen(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    q = queue.Queue()
    for stream, tag in ((proc.stdout, "out"), (proc.stderr, "err")):
        threading.Thread(target=_pump, args=(stream, q, tag), daemon=True).start()
    out_lines, err_lines = [], []
    open_streams, result_seen_at, timed_out = 2, None, False
    print(f"    (follow live: tail -f {log_path})", flush=True)
    with log_path.open("w") as log:
        while open_streams:
            now = time.time()
            if now - start > args.timeout:
                timed_out = True
                break
            if result_seen_at and now - result_seen_at > 15:
                break
            try:
                tag, line = q.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                open_streams -= 1
                continue
            if tag == "out":
                out_lines.append(line)
                log.write(line)
                log.flush()
                if '"type":"result"' in line.replace(" ", ""):
                    result_seen_at = time.time()
            else:
                err_lines.append(line)
    stop_process_tree(proc, repo)
    err = "".join(err_lines)
    (log_path.parent / "agent_stderr.txt").write_text(err)
    if not out_lines:
        sys.exit("\nClaude Code did not run. Command:\n  " + " ".join(cmd[:3]) + " ...\n"
                 f"Error output:\n{err.strip()[:2000] or '(empty)'}")
    stats = parse_stream(out_lines)
    if stats["is_error"] and stats["tool_calls"] == 0 and not timed_out:
        sys.exit(f"\nClaude Code returned an error before doing anything:\n  {stats['final_message']}")
    stats["timed_out"] = timed_out
    if timed_out or not stats["duration_s"]:
        stats["duration_s"] = round(time.time() - start, 1)
    return stats


def _pump(stream, q, tag):
    for line in iter(stream.readline, ""):
        q.put((tag, line))
    q.put((tag, None))


def stop_process_tree(proc, repo):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            break
        try:
            proc.wait(timeout=10)
            break
        except subprocess.TimeoutExpired:
            continue
    sh(f"pkill -f '{repo}' 2>/dev/null; true")
    stop_local_servers()


def collect_evidence(repo, task, stats):
    ev = {}
    theme = repo / "themes" / "dot-org-hugo-theme"
    ev["theme_files_before_grading"] = len(list(theme.iterdir())) if theme.exists() else 0
    ev["node_modules_before_grading"] = (repo / "node_modules").exists()
    _, ev["hugo_version"] = sh("node_modules/.bin/hugo version 2>&1 || echo 'no hugo in node_modules'", cwd=repo)
    _, ev["git_status"] = sh("git status --porcelain --untracked-files=all -- . ':!node_modules' ':!public' ':!resources'", cwd=repo)
    _, diff = sh("git diff -- . ':!package-lock.json'", cwd=repo)
    _, new_files = sh("git ls-files --others --exclude-standard -- content static config | head -20 | "
                      "while read f; do echo \"=== $f\"; head -c 3000 \"$f\" | iconv -c -t UTF-8; echo; done", cwd=repo)
    ev["diff_and_new_files"] = (diff + "\n" + new_files)[:20000]
    if ev["theme_files_before_grading"] == 0:
        sh("git submodule update --init --recursive", cwd=repo, timeout=1800)
    if not ev["node_modules_before_grading"]:
        sh("npm ci --no-audit --no-fund || npm install --no-audit --no-fund", cwd=repo, timeout=1800)
    code, out = sh("npm run build", cwd=repo, timeout=1800)
    ev["build_exit_code"] = code
    ev["build_output_tail"] = "\n".join(out.splitlines()[-25:])
    ev["probes"] = {p: sh(p, cwd=repo)[1][:3000] for p in task["probes"]}
    ev["agent_commands"] = stats["commands"][:150]
    ev["agent_final_message"] = (stats["final_message"] or "")[:6000]
    return ev


JUDGE_PROMPT = """You are grading one run of a coding agent on the todogroup.org Hugo website repo.
Judge ONLY from the evidence below. Do not guess. If the evidence does not show that a criterion is met, it fails.

Notes on the evidence:
- theme_files_before_grading and node_modules_before_grading show the repo state when the agent finished.
- After that, the grader initialized the submodule and installed dependencies itself if needed, then ran `npm run build`.
  Use build_exit_code and build_output_tail for criteria about the site building, and probes for the build output.
- agent_commands lists every tool call the agent made (Bash commands, or [Tool] path).

TASK GIVEN TO THE AGENT:
{task}

CRITERIA:
{criteria}

EVIDENCE (JSON):
{evidence}

Reply with ONLY a JSON object, no code fences, in this shape:
{{"<criterion id>": {{"pass": true or false, "reason": "<one short sentence>"}}, ...}}
Include every criterion id listed above."""


def judge(task, evidence, args):
    criteria_txt = "\n".join(f"- {c['id']}: {c['prompt']}" for c in task["criteria"])
    prompt = JUDGE_PROMPT.format(task=task["prompt"], criteria=criteria_txt,
                                 evidence=json.dumps(evidence, ensure_ascii=False, indent=1))
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "1",
           "--disallowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch"]
    if args.judge_model:
        cmd += ["--model", args.judge_model]
    with tempfile.TemporaryDirectory() as empty:
        p = subprocess.run(cmd, cwd=empty, capture_output=True, text=True, timeout=600)
    try:
        text = json.loads(p.stdout).get("result", "")
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        verdicts = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception:
        sys.exit("\nThe judge call failed.\nError output:\n" + (p.stderr.strip()[:2000] or "(empty)")
                 + "\nOutput:\n" + (p.stdout.strip()[:2000] or "(empty)"))
    return verdicts


def apply_graph(task, verdicts):
    final = {}
    for c in task["criteria"]:
        if any(final.get(p, {}).get("status") != "pass" for p in c["dependsOn"]):
            final[c["id"]] = {"status": "skipped", "reason": "a parent criterion did not pass"}
            continue
        v = verdicts.get(c["id"])
        if v is None:
            final[c["id"]] = {"status": "fail", "reason": "judge gave no verdict"}
        else:
            final[c["id"]] = {"status": "pass" if v.get("pass") else "fail", "reason": v.get("reason", "")}
    return final


def write_summary(rows, path):
    lines = ["# todogroup.org AX eval: summary", "",
             "| Task | Condition | Runs | All criteria passed | Criteria passed | Tool calls | Tokens | Time (s) | Cost (USD) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    keys = sorted({(r["task_id"], r["condition"]) for r in rows})
    mean = lambda xs: statistics.mean(xs) if xs else 0
    for task_id, cond in keys:
        rs = [r for r in rows if r["task_id"] == task_id and r["condition"] == cond]
        n = len(rs)
        ok = sum(1 for r in rs if str(r["all_passed"]) == "True")
        crit = mean([int(r["criteria_passed"]) / max(1, int(r["criteria_total"])) for r in rs])
        num = lambda k: [float(r[k]) for r in rs if str(r[k]) not in ("", "None")]
        lines.append(f"| {task_id} | {cond} | {n} | {ok}/{n} | {crit:.0%} | {mean(num('tool_calls')):.1f} | "
                     f"{mean(num('tokens_total')):,.0f} | {mean(num('duration_s')):.0f} | {mean(num('cost_usd')):.2f} |")
    lines += ["", "Means across runs. Tokens include cache reads. Read the per-run reasons in runs/*/*/*/grade.json."]
    path.write_text("\n".join(lines) + "\n")


def save_rows(rows, results_csv):
    with results_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, restval="")
        w.writeheader()
        w.writerows(rows)


def regrade(args, tasks):
    if shutil.which("claude") is None:
        sys.exit("Claude Code (claude) is not on PATH.")
    results_csv = HERE / "results.csv"
    if not results_csv.exists():
        sys.exit("No results.csv to regrade.")
    rows = list(csv.DictReader(results_csv.open()))
    todo = [r for r in rows if r["task_id"] in tasks]
    print(f"Regrading {len(todo)} runs (judge only, no agent runs)")
    for i, r in enumerate(todo, 1):
        task, run_dir = tasks[r["task_id"]], HERE / r["run_dir"]
        repo, ev_path = run_dir / "repo", run_dir / "evidence.json"
        if not ev_path.exists() or not repo.exists():
            print(f"[{i}/{len(todo)}] {r['run_dir']}: missing evidence or repo, skipped")
            continue
        evidence = json.loads(ev_path.read_text())
        evidence["probes"] = {p: sh(p, cwd=repo)[1][:3000] for p in task["probes"]}
        ev_path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False))
        final = apply_graph(task, judge(task, evidence, args))
        (run_dir / "grade.json").write_text(json.dumps(final, indent=1, ensure_ascii=False))
        passed = sum(1 for v in final.values() if v["status"] == "pass")
        r.update({"all_passed": str(passed == len(final)), "criteria_passed": str(passed),
                  "criteria_total": str(len(final)),
                  "failed_criteria": " ".join(k for k, v in final.items() if v["status"] != "pass")})
        print(f"[{i}/{len(todo)}] {r['task_id']} | {r['condition']} | rep {r['repetition']}: {passed}/{len(final)}", flush=True)
        save_rows(rows, results_csv)
    write_summary(rows, HERE / "summary.md")
    print(f"\nDone. See {HERE / 'summary.md'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fork-user", required=True, help="GitHub user that holds the eval branches")
    ap.add_argument("--tasks", default="t1,t2,t6", help="comma-separated task prefixes, or 'all'")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conditions", default="with,without")
    ap.add_argument("--model", default="", help="model for the agent (default: Claude Code's default)")
    ap.add_argument("--grader-model", "--judge-model", dest="judge_model", default="", help="model for the grader (default: Claude Code's default)")
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--timeout", type=int, default=1500, help="seconds per agent run")
    ap.add_argument("--dry-run", action="store_true", help="only print the plan")
    ap.add_argument("--regrade", action="store_true",
                    help="re-run only the evidence checks and the judge on finished runs (no agent runs)")
    args = ap.parse_args()

    spec = json.loads((HERE / "eval.json").read_text())
    wanted = None if args.tasks == "all" else [t.strip() for t in args.tasks.split(",")]
    tasks = [t for t in spec["tasks"] if wanted is None or any(t["id"].startswith(w + "_") or t["id"] == w for w in wanted)]
    if args.regrade:
        regrade(args, {t["id"]: t for t in tasks})
        return
    conds = [c.strip() for c in args.conditions.split(",")]
    plan = [(t, c, r) for r in range(1, args.reps + 1) for t in tasks for c in conds]
    print(f"{len(plan)} runs: {len(tasks)} tasks x {len(conds)} conditions x {args.reps} repetitions")
    if args.dry_run:
        for t, c, r in plan:
            print(f"  {t['id']:<24} {c:<8} rep {r}")
        return
    if shutil.which("claude") is None:
        sys.exit("Claude Code (claude) is not on PATH.")

    cache, runs_root = HERE / ".cache", HERE / "runs"
    prepare_cache(args.fork_user, cache)
    results_csv = HERE / "results.csv"
    rows = list(csv.DictReader(results_csv.open())) if results_csv.exists() else []
    done = {(r["task_id"], r["condition"], r["repetition"]) for r in rows}

    for i, (task, cond, rep) in enumerate(plan, 1):
        key = (task["id"], cond, str(rep))
        if key in done:
            print(f"[{i}/{len(plan)}] {key} already done, skipping")
            continue
        run_dir = runs_root / task["id"] / cond / f"rep{rep}"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        repo = run_dir / "repo"
        print(f"[{i}/{len(plan)}] {task['id']} | {cond} | rep {rep}: agent running...", flush=True)
        fresh_copy(cache, cond, repo)
        stats = run_agent(repo, task["prompt"], args, run_dir / "transcript.jsonl")
        stop_local_servers()
        print(f"    {stats['tool_calls']} tool calls, {stats['tokens_total']:,} tokens, {stats['duration_s']} s. Grading...", flush=True)
        evidence = collect_evidence(repo, task, stats)
        (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=1, ensure_ascii=False))
        final = apply_graph(task, judge(task, evidence, args))
        (run_dir / "grade.json").write_text(json.dumps(final, indent=1, ensure_ascii=False))
        passed = sum(1 for v in final.values() if v["status"] == "pass")
        row = {
            "task_id": task["id"], "condition": cond, "repetition": rep,
            "all_passed": passed == len(final), "criteria_passed": passed, "criteria_total": len(final),
            **{k: stats[k] for k in ["tool_calls", "num_turns", "tokens_total", "input_tokens", "output_tokens",
                                     "cache_read_tokens", "cache_creation_tokens", "duration_s", "cost_usd", "timed_out"]},
            "run_dir": str(run_dir.relative_to(HERE)),
            "failed_criteria": " ".join(k for k, v in final.items() if v["status"] != "pass"),
        }
        rows.append({k: str(v) for k, v in row.items()})
        with results_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)
        shutil.rmtree(repo / "node_modules", ignore_errors=True)
        print(f"    {passed}/{len(final)} criteria passed", flush=True)
        write_summary(rows, HERE / "summary.md")

    write_summary(rows, HERE / "summary.md")
    print(f"\nDone. See {HERE / 'summary.md'} and {results_csv}")


if __name__ == "__main__":
    main()
