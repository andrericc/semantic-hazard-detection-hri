#!/usr/bin/env bash
set -euo pipefail

STACK="${ROBOT_STACK:-tiago}"

case "$STACK" in
  booster)
    exec /app/entrypoint_booster.sh "$@"
    ;;
  tiago)
    exec /app/entrypoint_tiago.sh "$@"
    ;;
  *)
    echo "[entrypoint] Unknown ROBOT_STACK='$STACK' (expected 'booster' or 'tiago')" >&2
    exit 2
    ;;
esac
