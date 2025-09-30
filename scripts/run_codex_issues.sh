#!/usr/bin/env bash
set -Eeuo pipefail

# QMTL Codex Issue Orchestrator (parallel-only)
# - Always runs issues in parallel using per-issue git worktrees
# - Each child worktree executes exactly one issue via a single codex exec
# - DECISION CONTRACT: Scheduler decisions rely ONLY on artifacts (.last/.changes/.verify);
#   streaming console output is IGNORED for scheduling (but preserved to *.console.txt for auditing).
# - Optional: verify (preflight/full), PR creation/merge, and cleanup

usage() {
  cat <<'USAGE'
Usage: scripts/run_codex_issues.sh -f ISSUE_SCOPE_FILE -i "ID1 ID2 ..." [options]

Required:
  -f, --file PATH           Path to issue scope file (Markdown/YAML/JSON)
  -i, --ids  "LIST"         Space-separated issue IDs (e.g., "761 762 763")

Options (minimal):
  -p, --prompt PATH         Prompt file (default: codex_prompts/qmtl_issue_runner.prompt.md)
  -C, --repo   PATH         Repo root as working dir (default: .)
  -o, --outdir PATH         Output dir for artifacts (default: .codex_runs)
  --parallel N|auto         Max concurrent issues (default: auto)
  --verify                  Run preflight tests and docs build per issue
  --merge                   Auto-merge per-issue PR when status is Done (squash)
  -h, --help                Show this help

Behavior (opinionated defaults):
  - Creates a Draft PR per issue on first pass and updates it on follow-ups.
  - Uses stable branch names: issue/<ID>-codex.
  - Posts the latest .last.txt as a PR comment each pass.
  - Artifacts (.codex_runs/, .codex_worktrees/) are never committed.
USAGE
}

ISSUE_SCOPE_FILE=${ISSUE_SCOPE_FILE:-}
ISSUE_IDS=${ISSUE_IDS:-}
PROMPT_FILE=${PROMPT_FILE:-codex_prompts/qmtl_issue_runner.prompt.md}
REPO_DIR=${REPO_DIR:-.}
OUT_DIR=${OUT_DIR:-.codex_runs}
MAX_FOLLOWUPS=${MAX_FOLLOWUPS:-1}
VERIFY=${VERIFY:-0}
ENABLE_MERGE=${ENABLE_MERGE:-0}
GIT_BASE=${GIT_BASE:-}
GIT_REMOTE=${GIT_REMOTE:-origin}
REQUIRE_CLEAN=${REQUIRE_CLEAN:-1}
STASH_WIP=${STASH_WIP:-0}
PARALLEL=${PARALLEL:-auto}
WORKTREES_DIR=${WORKTREES_DIR:-.codex_worktrees}
CLEANUP_WORKTREES=${CLEANUP_WORKTREES:-1}
CLEANUP_ON_DONE=${CLEANUP_ON_DONE:-0}
CLEANUP_SCOPE=${CLEANUP_SCOPE:-0}
# Opinionated defaults
STABLE_BRANCHES=1
ALLOW_EMPTY_PR=0
PR_DRAFT_ALWAYS=1
MERGE_METHOD=squash

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--file) ISSUE_SCOPE_FILE="$2"; shift 2;;
    -i|--ids) ISSUE_IDS="$2"; shift 2;;
    -p|--prompt) PROMPT_FILE="$2"; shift 2;;
    -C|--repo) REPO_DIR="$2"; shift 2;;
    -o|--outdir) OUT_DIR="$2"; shift 2;;
    --verify) VERIFY=1; shift;;
    --merge) ENABLE_MERGE=1; shift;;
    --parallel) PARALLEL="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

command -v codex >/dev/null 2>&1 || { echo "codex CLI not found in PATH" >&2; exit 127; }
[[ -f "$PROMPT_FILE" ]] || { echo "Prompt file not found: $PROMPT_FILE" >&2; exit 1; }
[[ -n "$ISSUE_SCOPE_FILE" && -f "$ISSUE_SCOPE_FILE" ]] || { echo "Issue scope file missing: use -f PATH" >&2; exit 1; }
[[ -n "$ISSUE_IDS" ]] || { echo "No issue IDs provided: use -i \"752 753\"" >&2; exit 1; }

# Resolve auto parallelism
if [[ "$PARALLEL" == "auto" ]]; then
  if command -v nproc >/dev/null 2>&1; then
    cores=$(nproc || echo 2)
  else
    cores=$(sysctl -n hw.ncpu 2>/dev/null || echo 2)
  fi
  issues_count=$(echo "$ISSUE_IDS" | wc -w | tr -d ' ')
  PARALLEL=$(( issues_count < cores ? issues_count : cores ))
  if [[ "$PARALLEL" -lt 1 ]]; then PARALLEL=1; fi
fi

# Utilities shared by child
run_codex_once() {
  local issue_id="$1"; shift
  local pass_idx="$1"; shift
  local out_last="$OUT_DIR/${issue_id}.pass${pass_idx}.last.txt"
  local out_console="$OUT_DIR/${issue_id}.pass${pass_idx}.console.txt"
  local approval_args=("-a" "never")
  echo "[run] ISSUE_ID=$issue_id pass=$pass_idx"
  ISSUE_SCOPE_FILE="$ISSUE_SCOPE_FILE" ISSUE_ID="$issue_id" \
  codex -s danger-full-access ${approval_args[@]:-} -c shell_environment_policy.inherit=all \
        exec -C "$REPO_DIR" --color never \
        --output-last-message "$out_last" - < "$PROMPT_FILE" 2>&1 | tee "$out_console"
}

record_changes() {
  local pass_label="$1"; shift
  local changes_file="$OUT_DIR/${pass_label}.changes.txt"
  {
    echo "# git status --porcelain"; git -C "$REPO_DIR" status --porcelain || true
    echo;
    echo "# git diff --name-only"; git -C "$REPO_DIR" diff --name-only || true
    echo;
    echo "# git diff --stat"; git -C "$REPO_DIR" diff --stat || true
  } > "$changes_file" 2>&1 || true
}

verify_run() {
  local pass_label="$1"; shift
  local verify_file="$OUT_DIR/${pass_label}.verify.txt"
  {
    echo "[verify] preflight tests";
    PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q -k 'not slow' --timeout=60 --timeout-method=thread --maxfail=1 || exit 10
    echo;
    echo "[verify] docs build";
    uv run mkdocs build || exit 11
  } > "$verify_file" 2>&1 || return $?
  return 0
}

extract_followups() {
  local file="$1"
  awk '
    BEGIN{found=0}
    tolower($0) ~ /next[[:punct:] ]*run[[:punct:] ]*instructions/ {found=1; next}
    found && $0 ~ /^[[:space:]]*[-*][[:space:]]+/ {
      line=$0; sub(/^[[:space:]]*[-*][[:space:]]+/,"",line);
      gsub(/^[[:space:]]+|[[:space:]]+$/,"",line);
      if (line != "") { if (acc != "") acc = acc "; " line; else acc = line }
      next
    }
    found && NF==0 { exit }
    END{ if (acc != "") print acc }
  ' "$file" || true
}

needs_followup() {
  local file="$1"
  # Primary signal: explicit status line
  if grep -qiE '^Result[[:space:]]+status:.*needs[[:space:]-]*follow' "$file"; then
    return 0
  fi
  # Secondary signal: presence of Next-run Instructions section
  if grep -qiE '^Next[[:punct:] ]*run[[:punct:] ]*instructions' "$file"; then
    return 0
  fi
  return 1
}

ensure_git_clean_or_stash() {
  if [[ "$REQUIRE_CLEAN" == 1 ]]; then
    if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
      echo "[error] Working tree not clean. Commit or stash changes, or use --stash-wip" >&2
      exit 20
    fi
  elif [[ "$STASH_WIP" == 1 ]]; then
    git -C "$REPO_DIR" stash push -u -m "codex-orchestrator-pre" >/dev/null || true
  fi
}

restore_stash_if_any() {
  if [[ "$STASH_WIP" == 1 ]]; then
    local has=$(git -C "$REPO_DIR" stash list | head -n1 | grep -c "codex-orchestrator-pre" || true)
    if [[ "$has" -gt 0 ]]; then
      git -C "$REPO_DIR" stash pop || true
    fi
  fi
}

current_branch() {
  git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD
}

derive_owner_repo() {
  local url
  url=$(git -C "$REPO_DIR" remote get-url "$GIT_REMOTE" 2>/dev/null || true)
  echo "$url" | sed -E 's#(git@github.com:|https?://github.com/)##; s#\.git$##'
}

start_feature_branch() {
  local issue_id="$1"; shift
  local base_branch="$GIT_BASE"
  if [[ -z "$base_branch" ]]; then
    base_branch=$(current_branch)
  fi
  local branch
  if [[ "$STABLE_BRANCHES" == 1 ]]; then
    branch="issue/${issue_id}-codex"
  else
    branch="issue/${issue_id}-codex-$(date +%Y%m%d%H%M%S)"
  fi
  git -C "$REPO_DIR" fetch "$GIT_REMOTE" "$base_branch" >/dev/null 2>&1 || true
  # Try to reuse existing branch when stable-branches enabled
  if [[ "$STABLE_BRANCHES" == 1 ]] && git -C "$REPO_DIR" rev-parse --verify -q "$branch" >/dev/null; then
    git -C "$REPO_DIR" checkout "$branch" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" rebase "$GIT_REMOTE/$base_branch" >/dev/null 2>&1 || true
  else
    git -C "$REPO_DIR" checkout -B "$branch" "$GIT_REMOTE/$base_branch" >/dev/null 2>&1 || git -C "$REPO_DIR" checkout -b "$branch" || true
  fi
  echo "$branch"
}

commit_changes_for_issue() {
  local issue_id="$1"; shift || true
  local last_file="$1"; shift || true
  local status_line="$1"; shift || true
  local msg_file="$OUT_DIR/${issue_id}.commitmsg.txt"
  awk '
    BEGIN{take=0}
    tolower($0) ~ /suggested commit message/ {take=1; next}
    take && NF==0 {exit}
    take {print}
  ' "$last_file" > "$msg_file.tmp" || true
  if [[ ! -s "$msg_file.tmp" ]]; then
    {
      if echo "$status_line" | grep -qi 'done'; then
        echo "chore: apply Codex changes for issue $issue_id"
        echo
        echo "Fixes #$issue_id"
      else
        echo "chore: partial changes for issue $issue_id"
        echo
        echo "Refs #$issue_id"
      fi
    } > "$msg_file"
  else
    cp "$msg_file.tmp" "$msg_file"
    if ! grep -qE "(Fixes|Closes|Resolves) #$issue_id" "$msg_file"; then
      echo >> "$msg_file"
      echo "Fixes #$issue_id" >> "$msg_file"
    fi
  fi
  rm -f "$msg_file.tmp" 2>/dev/null || true
  git -C "$REPO_DIR" add -A
  # Guard: never stage orchestrator artifacts
  git -C "$REPO_DIR" reset -q -- .codex_runs .codex_worktrees 2>/dev/null || true
  if ! git -C "$REPO_DIR" diff --cached --quiet; then
    git -C "$REPO_DIR" commit -F "$msg_file" || return 30
    echo "$msg_file"
  else
    if [[ "$ALLOW_EMPTY_PR" == 1 ]]; then
      git -C "$REPO_DIR" commit --allow-empty -F "$msg_file" || return 30
      echo "$msg_file"
    else
      echo ""
    fi
  fi
}

create_pr_and_maybe_merge() {
  local issue_id="$1"; shift
  local branch="$1"; shift
  local base_branch="$GIT_BASE"
  local draft_mode=${1:-0}
  shift || true
  if [[ -z "$base_branch" ]]; then
    base_branch=$(current_branch)
  fi
  git -C "$REPO_DIR" push -u "$GIT_REMOTE" "$branch" || return 40
  local pr_url=""
  if command -v gh >/dev/null 2>&1; then
    # If a PR already exists for this branch, reuse it
    local existing
    existing=$(gh -R "$(derive_owner_repo)" pr view "$branch" --json url --jq .url 2>/dev/null || true)
    if [[ -n "$existing" ]]; then
      pr_url="$existing"
    else
      local draft_flag=()
      [[ "$draft_mode" == 1 ]] && draft_flag+=(--draft)
      pr_url=$(gh -R "$(derive_owner_repo)" pr create --head "$branch" --base "$base_branch" ${draft_flag[@]} --title "Issue #$issue_id" --body "Automated PR for issue #$issue_id" 2>/dev/null || true)
    fi
  elif [[ -n "${GITHUB_TOKEN:-${GH_TOKEN:-}}" ]]; then
    local owner_repo
    owner_repo=$(derive_owner_repo)
    local title="Issue #$issue_id"
    local body="Automated PR for issue #$issue_id"
    pr_url=$(curl -fsSL -X POST -H "Authorization: Bearer ${GITHUB_TOKEN:-$GH_TOKEN}" -H "Accept: application/vnd.github+json" \
      -d "{\"title\":\"$title\",\"head\":\"$branch\",\"base\":\"$base_branch\",\"body\":\"$body\"}" \
      "https://api.github.com/repos/${owner_repo}/pulls" | jq -r '.html_url // empty' 2>/dev/null || true)
  else
    echo "[warn] Neither gh nor GITHUB_TOKEN available; skipping PR creation" >&2
  fi
  [[ -n "$pr_url" ]] && echo "$pr_url" || echo ""
}

merge_pr_if_requested() {
  local pr_url="$1"; shift
  local branch="$1"; shift
  local ready_first=${1:-0}
  shift || true
  if [[ "$ENABLE_MERGE" != 1 || -z "$pr_url" ]]; then
    return 0
  fi
  if command -v gh >/dev/null 2>&1; then
    if [[ "$ready_first" == 1 ]]; then
      gh pr ready "$pr_url" -R "$(derive_owner_repo)" >/dev/null 2>&1 || true
    fi
    gh pr merge "$pr_url" -R "$(derive_owner_repo)" -d -${MERGE_METHOD:0:1} || true
  elif [[ -n "${GITHUB_TOKEN:-${GH_TOKEN:-}}" ]]; then
    local owner_repo pr_number
    owner_repo=$(derive_owner_repo)
    pr_number=$(echo "$pr_url" | sed -E 's#.*/pull/(\d+).*#\1#')
    curl -fsSL -X PUT -H "Authorization: Bearer ${GITHUB_TOKEN:-$GH_TOKEN}" -H "Accept: application/vnd.github+json" \
      -d "{\"merge_method\":\"$MERGE_METHOD\"}" \
      "https://api.github.com/repos/${owner_repo}/pulls/${pr_number}/merge" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" push "$GIT_REMOTE" --delete "$branch" >/dev/null 2>&1 || true
  else
    echo "[warn] Cannot merge PR automatically (no gh/GITHUB_TOKEN)." >&2
  fi
}

# Parent: parallel orchestration using worktrees
if [[ "${RUN_AS_CHILD:-0}" != "1" ]]; then
  # Build absolute paths for prompt/scope/outdir
  ABS_PROMPT="$PROMPT_FILE"; ABS_SCOPE="$ISSUE_SCOPE_FILE"; ABS_OUT_DIR="$OUT_DIR"
  if [[ ! "$ABS_PROMPT" = /* ]]; then ABS_PROMPT="$(cd "$(dirname "$PROMPT_FILE")" && pwd)/$(basename "$PROMPT_FILE")"; fi
  if [[ ! "$ABS_SCOPE" = /* ]]; then ABS_SCOPE="$(cd "$(dirname "$ISSUE_SCOPE_FILE")" && pwd)/$(basename "$ISSUE_SCOPE_FILE")"; fi
  if [[ ! "$ABS_OUT_DIR" = /* ]]; then ABS_OUT_DIR="$(cd "$(dirname "$OUT_DIR")" && pwd)/$(basename "$OUT_DIR")"; fi
  mkdir -p "$ABS_OUT_DIR"

  # Derive base branch
  base_branch="$GIT_BASE"
  if [[ -z "$base_branch" ]]; then
    base_branch=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)
  fi

  mkdir -p "$WORKTREES_DIR"
  pids=()
  for id in $ISSUE_IDS; do
    wt_dir="$WORKTREES_DIR/issue-$id"
    wt_branch="issue/${id}-codex-$(date +%Y%m%d%H%M%S)"
    git -C "$REPO_DIR" fetch "$GIT_REMOTE" "$base_branch" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" worktree add -B "$wt_branch" "$wt_dir" "$GIT_REMOTE/$base_branch" >/dev/null 2>&1 \
      || git -C "$REPO_DIR" worktree add -b "$wt_branch" "$wt_dir" "$GIT_REMOTE/$base_branch" >/dev/null 2>&1 \
      || git -C "$REPO_DIR" worktree add "$wt_dir" "$GIT_REMOTE/$base_branch" >/dev/null 2>&1

    echo "[parallel] spawned worktree $wt_dir (branch $wt_branch) for issue $id"

    # Build child args
    child_args=( -f "$ABS_SCOPE" -i "$id" -p "$ABS_PROMPT" -C "$wt_dir" -o "$ABS_OUT_DIR" )
    [[ "$VERIFY" == 1 ]] && child_args+=(--verify)
    [[ "$ENABLE_MERGE" == 1 ]] && child_args+=(--merge)

    RUN_AS_CHILD=1 bash "$0" "${child_args[@]}" &
    pids+=("$!")

    # Throttle
    while (( $(jobs -pr | wc -l | tr -d ' ') >= PARALLEL )); do
      sleep 1
    done
  done

  # Wait for all children
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done

  # Cleanup worktrees if requested
  if [[ "$CLEANUP_WORKTREES" == 1 ]]; then
    for id in $ISSUE_IDS; do
      wt_dir="$WORKTREES_DIR/issue-$id"
      git -C "$REPO_DIR" worktree remove -f "$wt_dir" >/dev/null 2>&1 || true
      rm -rf "$wt_dir" 2>/dev/null || true
    done
  fi

  if [[ "$CLEANUP_SCOPE" == 1 ]]; then
    rm -f "$ISSUE_SCOPE_FILE" 2>/dev/null || true
  fi

  exit 0
fi

# Child: run a single issue in this worktree
ensure_git_clean_or_stash

summaries=()
for id in $ISSUE_IDS; do
  pass=1
  run_codex_once "$id" "$pass" || true
  last_file="$OUT_DIR/${id}.pass${pass}.last.txt"
  if [[ ! -s "$last_file" ]]; then
    echo "[warn] No last message captured for issue $id (pass $pass)" >&2
  fi

  if needs_followup "$last_file"; then
    if (( pass <= MAX_FOLLOWUPS )); then
      followups=$(extract_followups "$last_file" || true)
      pass=$((pass+1))
      echo "[follow-up] ISSUE_ID=$id pass=$pass instructions: ${followups:-<none>}"
      FOLLOW_UP_INSTRUCTIONS="$followups" run_codex_once "$id" "$pass" || true
    else
      echo "[skip] Reached max follow-ups for issue $id"
    fi
  fi

  pass_label="${id}.pass${pass}"
  record_changes "$pass_label"
  verify_status="skipped"
  if [[ "$VERIFY" == 1 ]]; then
    if verify_run "$pass_label"; then
      verify_status="passed"
    else
      verify_status="failed($?)"
    fi
  fi

  # Orchestrator-owned status decision (artifact-driven)
  status="unknown"
  changes_file="$OUT_DIR/${id}.pass${pass}.changes.txt"
  # Count changed files from the recorded diff section
  changed_count=$(awk '
    /^# git diff --name-only/ {take=1; next}
    take && NF==0 {exit}
    take && $0 !~ /^#/ {print}
  ' "$changes_file" 2>/dev/null | wc -l | tr -d ' ' || echo 0)

  has_next_instr=0
  if grep -qiE '^Next[[:punct:] ]*run[[:punct:] ]*instructions' "$OUT_DIR/${id}.pass${pass}.last.txt" 2>/dev/null; then
    has_next_instr=1
  fi

  if [[ "$VERIFY" == 1 ]]; then
    if [[ "$verify_status" == "passed" ]]; then
      status="Done"
    else
      status="Needs follow-up"
    fi
  else
    if [[ "$has_next_instr" == 1 ]]; then
      status="Needs follow-up"
    elif (( changed_count > 0 )); then
      status="Done"
    else
      status="Blocked"
    fi
  fi
  summaries+=("$id:$status:pass=$pass:last=$OUT_DIR/${id}.pass${pass}.last.txt:verify=$verify_status")

  # Create or update PRs according to flags
  # Draft PRs are created only when there are actual changes (no empty commits)
    feature_branch=$(start_feature_branch "$id")
    commit_msg_file=$(commit_changes_for_issue "$id" "$OUT_DIR/${id}.pass${pass}.last.txt" "$status") || true
    if [[ -n "$commit_msg_file" ]]; then
      pr_url=$(create_pr_and_maybe_merge "$id" "$feature_branch" 1)
      if [[ -n "$pr_url" ]]; then
        # Post a short progress comment
        if command -v gh >/dev/null 2>&1; then
          gh -R "$(derive_owner_repo)" pr comment "$pr_url" -F "$OUT_DIR/${id}.pass${pass}.last.txt" >/dev/null 2>&1 || true
        fi
        # Merge if requested and Done
        if [[ "$ENABLE_MERGE" == 1 && "$status" == "Done" ]]; then
          merge_pr_if_requested "$pr_url" "$feature_branch" 1
        fi
      fi
    else
      echo "[info] No changes for issue $id; skipping PR creation"
    fi
  

  if [[ "$CLEANUP_ON_DONE" == 1 && "$status" == "Done" ]]; then
    rm -f \
      "$OUT_DIR/${id}.pass"*".last.txt" \
      "$OUT_DIR/${id}.pass"*".changes.txt" \
      "$OUT_DIR/${id}.pass"*".verify.txt" \
      "$OUT_DIR/${id}.pass"*".console.txt" 2>/dev/null || true
  fi

  # Note: PR is always present per issue; above block handles merge when Done
done

echo "\nSummary:"
printf '%s\n' "${summaries[@]}"

restore_stash_if_any
