#!/usr/bin/env bash
set -euo pipefail

# Booster runtime environment
export LD_LIBRARY_PATH="/app/booster_motion/lib:/app/booster_motion/lib-usr-local:/app/booster_motion/lib-x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-/app/booster_motion/fastdds_profile.xml}"

# Optional Maximus paths (used only if mounted/present)
if [[ -d /app/maximus/config ]]; then
  export SPQR_CONFIG_ROOT=/app/maximus/config
fi
if [[ -d /app/maximus/behaviors ]]; then
  export SPQR_BEHAVIOR_TREE_PATH=/app/maximus/behaviors
fi

# Allow override for debugging/custom runs
if [[ $# -gt 0 ]]; then
  exec "$@"
fi

if [[ -f /etc/supervisor/conf.d/booster.conf ]]; then
  exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/booster.conf
fi

echo "[entrypoint_booster] booster.conf not found, dropping to shell."
exec bash

