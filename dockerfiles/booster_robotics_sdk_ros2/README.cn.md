# booster_ros2_interface

booster_ros2_interface 是一个ROS 2接口包，为机器人控制提供了一系列的消息和服务定义。

## 概述

该接口包包含了多种消息类型和服务，可以用于机器人状态发布、命令控制、RPC服务调用等场景。主要包含以下内容：

- 各种消息定义（msg/目录下）：包括机器人低层状态（LowState）、电机状态（MotorState）、IMU数据（ImuState）等。
- 服务定义（srv/目录下）：包括RPC服务（RpcService）和代理服务（AgentService）。

## 消息类型

- **BoosterApiReqMsg/BoosterApiRespMsg**：用于API请求和响应消息。
- **ButtonEventMsg**：按钮事件消息。
- **FallDownState**：机器人跌倒状态消息。
- **HandCommand/HandDdsMsg/HandParam**：手部控制相关消息。
- **ImuState**：IMU传感器状态消息。
- **LowCmd/LowState**：低层命令和状态消息。
- **MotorCmd/MotorState**：电机命令和状态消息。
- **Odometer**：里程计消息。
- **RawBytesMsg**：原始字节消息。
- **RemoteControllerState**：遥控器状态消息。

## 服务类型

- **AgentService**：代理服务，用于字符串消息的请求和响应。
- **RpcService**：RPC服务，用于更复杂的数据交互。

## 使用方法

要使用这些消息和服务，请确保在您的ROS 2工作空间中正确安装并构建了此接口包。然后，您可以创建发布者、订阅者、客户端和服务端来使用这些定义的消息和服务。

## 依赖项

- ROS 2 (rclcpp)
- ament_cmake
- rosidl_default_generators
- rosidl_default_runtime

## 构建

要构建此包，请使用ROS 2的构建工具ament_cmake。确保所有依赖项都已安装，并运行`colcon build`命令。

## 贡献

欢迎贡献新的消息类型或改进现有的定义。请提交PR或Issue以讨论和贡献代码。

## 许可证

此项目目前使用默认的ROS 2许可证，请参阅LICENSE文件获取详细信息。