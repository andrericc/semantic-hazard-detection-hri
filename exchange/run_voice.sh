#!/bin/bash
# Launch the voice interface node. Run INSIDE the tiago_sim container from an
# INTERACTIVE shell (docker exec -it tiago_sim bash):
#   bash /root/exchange/exchange/run_voice.sh
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
unset FASTRTPS_DEFAULT_PROFILES_FILE          # .bashrc_addendum sets a broken booster profile
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp  # must match the detector's DDS
export HF_HUB_OFFLINE=1                       # whisper model is baked into the image
cd "$(dirname "$0")"
exec python3 voice_node.py
