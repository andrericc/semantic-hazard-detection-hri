# dockerfiles

Legacy Docker setup for the Booster T1 container (superseded by the root `Dockerfile`).

## Third-party SDKs

The following folders are copied from the official Booster Robotics repositories:

| Folder | Source |
|--------|--------|
| `booster_robotics_sdk/` | [BoosterRobotics/booster_robotics_sdk (main)](https://github.com/BoosterRobotics/booster_robotics_sdk/tree/main) |
| `booster_robotics_sdk_ros2/` | [BoosterRobotics/booster_robotics_sdk_ros_2 (main)](https://github.com/BoosterRobotics/booster_robotics_sdk_ros2/tree/main) |

They are included as plain files (not submodules) to avoid requiring external access at build time.
