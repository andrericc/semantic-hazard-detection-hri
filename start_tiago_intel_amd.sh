#!/bin/bash
# Start TIAGo simulation container with Intel/AMD GPU support
DOCKER_GPU_ARGS="--env DISPLAY \
  --env QT_X11_NO_MITSHM=1 \
  --volume=/tmp/.X11-unix:/tmp/.X11-unix:rw \
  --device=/dev/dri:/dev/dri"
DOCKER_COMMAND="docker run"
IMAGE_NAME="spqr:booster"
CONTAINER_NAME="tiago_sim"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNT_ARGS="-v ${SCRIPT_DIR}:/root/exchange"
DOCKER_SOCK_ARGS="-v /var/run/docker.sock:/var/run/docker.sock"
# PulseAudio passthrough for the voice interface (mic capture + espeak-ng playback)
PULSE_DIR="/run/user/$(id -u)/pulse"
AUDIO_ARGS="-v ${PULSE_DIR}:${PULSE_DIR} \
  -v ${HOME}/.config/pulse/cookie:/root/.config/pulse/cookie:ro \
  --env PULSE_SERVER=unix:${PULSE_DIR}/native"
xhost +local:docker
$DOCKER_COMMAND \
  $DOCKER_GPU_ARGS \
  $MOUNT_ARGS \
  $DOCKER_SOCK_ARGS \
  $AUDIO_ARGS \
  --env ROBOT_STACK=tiago \
  --net host \
  --privileged \
  --rm \
  -it \
  --name "$CONTAINER_NAME" \
  -w "/root/exchange" \
  "$IMAGE_NAME" \
  "/root/exchange/docker/entrypoint_tiago.sh"
