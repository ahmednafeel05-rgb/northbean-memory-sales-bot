#!/usr/bin/env bash
# S8 gate (design brief §13): "repo ready to share." Checks every deliverable the sprint's
# outcome names actually exists, plus the basic hygiene a shared repo needs.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

check() {
    if eval "$2"; then
        echo "OK   $1"
    else
        echo "FAIL $1"
        fail=1
    fi
}

check "README.md exists"                      "[ -f README.md ]"
check "README has a problem/intro section"     "grep -qi 'problem' README.md"
check "README has an architecture section"     "grep -qi 'architecture' README.md"
check "README has a results table"             "grep -qi '## Results' README.md"
check "README references the ADRs"             "grep -qi 'adr' README.md"
check "README has a next-steps/limitations section" "grep -qi 'out of scope\|next steps\|limitations' README.md"
check "demo GIF exists"                        "[ -f docs/demo.gif ]"
check "video script exists"                    "[ -f docs/video-script.md ]"

for n in 001 002 003 004 005 006 007; do
    check "ADR-$n exists" "ls adr/${n}-*.md >/dev/null 2>&1"
done

check ".env is gitignored, not tracked"        "! git ls-files --error-unmatch .env >/dev/null 2>&1"
check "no .env committed in git history"       "! git log --all --pretty=format: --name-only | grep -qx '\.env'"
check "docker-compose.yml exists"              "[ -f docker-compose.yml ]"
check "SESSION_LOG.md exists"                  "[ -f SESSION_LOG.md ]"

if [ "$fail" -eq 0 ]; then
    echo "ship-ready: all checks passed"
else
    echo "ship-ready: FAILED -- see FAIL lines above"
fi
exit "$fail"
