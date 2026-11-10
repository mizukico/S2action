#!/usr/bin/env bash
# Collect only small, failure-relevant S2Arm direct-library diagnostics.
set -uo pipefail

OUTPUT_DIR="${1:?usage: collect_diagnostics.sh OUTPUT_DIR DIAG_DIR}"
DIAG_DIR="${2:?usage: collect_diagnostics.sh OUTPUT_DIR DIAG_DIR}"
LOG_DIR="$OUTPUT_DIR/build/logs"
DIRECT_DIAG_DIR="$DIAG_DIR/direct-cache"

mkdir -p "$DIAG_DIR"

if [[ -d "$LOG_DIR" ]]; then
  cp -R "$LOG_DIR" "$DIAG_DIR/build-logs"
else
  echo "No upstream build log directory found at: $LOG_DIR"
fi

if [[ -f "$OUTPUT_DIR/events.jsonl" ]]; then
  cp "$OUTPUT_DIR/events.jsonl" "$DIAG_DIR/events.jsonl"
fi

# direct_lib.sh intentionally leaves failed work.stage.<pid> directories in
# the direct cache. Its --build-env preflight writes the actionable traceback
# to work.stage.<pid>/build_env.log, outside OUTPUT_DIR/build/logs.
declare -a CACHE_ROOTS=()
if [[ -n "${S2A_RUN_ROOT:-}" ]]; then
  CACHE_ROOTS+=("$S2A_RUN_ROOT/s2arm/cache/direct")
fi
CACHE_ROOTS+=("$HOME/.s2arm/run/s2arm/cache/direct")

declare -A SEEN_ROOTS=()
for cache_root in "${CACHE_ROOTS[@]}"; do
  [[ -n "$cache_root" && -d "$cache_root" ]] || continue
  [[ -n "${SEEN_ROOTS[$cache_root]:-}" ]] && continue
  SEEN_ROOTS["$cache_root"]=1

  echo "Searching direct-cache diagnostics: $cache_root"
  while IFS= read -r -d '' file; do
    relative="${file#"$cache_root"/}"
    destination="$DIRECT_DIAG_DIR/$relative"
    mkdir -p "$(dirname "$destination")"
    cp "$file" "$destination"
    echo "Collected: $relative"
  done < <(find "$cache_root" -type f -size -20M \\
    \\( -name 'build_env.log' -o -name 'profile_rows.txt' \\
       -o -name 'direct_lib.log' -o -name 'dsh_batch*.log' \\
       -o -name 'gl_shaders.log' -o -name 'vk_shaders.log' \\) -print0)
done

REFRESH_LOG="$LOG_DIR/refresh.log"
if [[ -f "$REFRESH_LOG" ]]; then
  echo "::group::S2Arm refresh.log (last 300 lines)"
  tail -n 300 "$REFRESH_LOG"
  echo "::endgroup::"
else
  echo "refresh.log was not generated."
  [[ ! -d "$LOG_DIR" ]] || find "$LOG_DIR" -maxdepth 2 -type f -print
fi

# Print the actual preflight error in the Actions log as well as preserving it
# in the diagnostic artifact. Do not dump arbitrary cache contents.
while IFS= read -r -d '' file; do
  echo "::group::$(basename "$file")"
  tail -n 120 "$file"
  echo "::endgroup::"
done < <(find "$DIRECT_DIAG_DIR" -type f -name 'build_env.log' -print0 2>/dev/null)

echo "Diagnostic files staged under: $DIAG_DIR"
find "$DIAG_DIR" -type f -print | sort
