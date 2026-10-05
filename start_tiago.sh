#!/bin/bash

# Start TIAGo simulation container with NVIDIA GPU support

DOCKER_GPU_ARGS="--env DISPLAY \
  --env QT_X11_NO_MITSHM=1 \
  --env __NV_PRIME_RENDER_OFFLOAD=1 \
  --env __GLX_VENDOR_LIBRARY_NAME=nvidia \
  --volume=/tmp/.X11-unix:/tmp/.X11-unix:rw"

dpkg -l | grep nvidia-container-toolkit &> /dev/null
HAS_NVIDIA_TOOLKIT=1
if [ $HAS_NVIDIA_TOOLKIT -eq 0 ]; then
  docker_version=$(docker version --format '{{.Client.Version}}' | cut -d. -f1)
  if [ "$docker_version" -ge 19 ]; then
    DOCKER_COMMAND="docker run --gpus all"
  else
    DOCKER_COMMAND="docker run --runtime=nvidia"
  fi
else
  echo "WARNING: nvidia-container-toolkit not found, running without GPU"
  DOCKER_COMMAND="docker run"
fi

IMAGE_NAME="spqr:booster"
CONTAINER_NAME="tiago_sim"

# Local folders mounted into container under /root/exchange
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNT_ARGS="-v ${SCRIPT_DIR}:/root/exchange"

# Allow circus (running inside this container) to control host Docker daemon
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
