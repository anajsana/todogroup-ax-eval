#!/usr/bin/env python3
import getpass
import os
import shutil
import socket
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"

replacements = [(str(Path.home()), "~"), (str(HERE), ".")]
user = getpass.getuser()
host = socket.gethostname().split(".")[0]
if user:
    replacements.append((user, "<user>"))
if host:
    replacements.append((host, "<computer>"))


def clean(text):
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def copy_clean(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(clean(src.read_text()))
    print(f"  {dst.relative_to(HERE)}")


if OUT.exists():
    shutil.rmtree(OUT)
print("Copied:")
for name in ("summary.md", "results.csv"):
    if (HERE / name).exists():
        copy_clean(HERE / name, OUT / name)
for grade in sorted((HERE / "runs").glob("*/*/rep*/grade.json")):
    task, cond, rep = grade.parts[-4:-1]
    copy_clean(grade, OUT / "grades" / task / cond / f"{rep}.json")
print("\nNot copied: transcripts and evidence files (they can contain local paths).")
print("Review results/ before you commit it.")
