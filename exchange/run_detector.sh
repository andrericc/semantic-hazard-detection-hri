#!/bin/bash
# Launch the anomaly detector node. Run INSIDE the tiago_sim container:
#   bash /root/exchange/exchange/run_detector.sh
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
unset FASTRTPS_DEFAULT_PROFILES_FILE          # .bashrc_addendum sets a broken booster profile
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp  # must match Gazebo's DDS
export HF_HUB_OFFLINE=1                       # use the model cache baked into the image
cd "$(dirname "$0")"                          # ./dataset paths + checkpoint are relative to here
exec python3 detector_node.py
