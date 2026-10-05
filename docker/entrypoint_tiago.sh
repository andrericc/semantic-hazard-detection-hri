#!/usr/bin/env bash
set -eo pipefail

set +u
if [[ -f /opt/ros/humble/setup.bash ]]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
fi

if [[ -f /root/tiago_public_ws/install/setup.bash ]]; then
  # shellcheck disable=SC1091
  source /root/tiago_public_ws/install/setup.bash
fi

# Project workspace (custom 'simulation' package: populated house world + robot teleport)
if [[ -f /root/exchange/install/setup.bash ]]; then
  # shellcheck disable=SC1091
  source /root/exchange/install/setup.bash
fi
set -u

export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
unset FASTRTPS_DEFAULT_PROFILES_FILE

# Allow a custom tiago launch command via env.
if [[ -n "${TIAGO_CMD:-}" ]]; then
  exec bash -lc "${TIAGO_CMD}"
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

exec bash
