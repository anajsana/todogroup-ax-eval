#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${1:?Give your GitHub user name, for example: ./setup-branches.sh <your-github-user>}"
HERE="$(cd "$(dirname "$0")" && pwd)"

git clone "https://github.com/${USER_NAME}/todogroup.org.git" todogroup-eval
cd todogroup-eval
git remote add upstream https://github.com/todogroup/todogroup.org.git
git fetch upstream main

git checkout -b eval/with-agents-md upstream/main
cp "$HERE/eval-cover.png" eval-cover.png
printf '@AGENTS.md\n' > CLAUDE.md
git add eval-cover.png CLAUDE.md
git commit -m "Eval: with AGENTS.md"

git checkout -b eval/without-agents-md upstream/main
cp "$HERE/eval-cover.png" eval-cover.png
git rm -q AGENTS.md
git add eval-cover.png
git commit -m "Eval: without AGENTS.md"

git push origin eval/with-agents-md eval/without-agents-md
echo "Done. Branches pushed to ${USER_NAME}/todogroup.org"
