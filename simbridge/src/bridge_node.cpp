#include "bridge_node.hpp"
#include <sys/types.h>

const std::map<std::string, std::vector<std::string>> BridgeNode::ROBOT_JOINTS_NAMES_MAP  = {
        {"Booster-T1", {"AAHead_yaw",
                "Head_pitch",
                "Left_Shoulder_Pitch",
                "Left_Shoulder_Roll",
                "Left_Elbow_Pitch",
                "Left_Elbow_Yaw",
                "Right_Shoulder_Pitch",
                "Right_Shoulder_Roll",
                "Right_Elbow_Pitch",
                "Right_Elbow_Yaw",
                "Waist",
                "Left_Hip_Pitch",
                "Left_Hip_Roll",
                "Left_Hip_Yaw",
                "Left_Knee_Pitch",
                "Left_Ankle_Pitch",
                "Left_Ankle_Roll",
                "Right_Hip_Pitch",
                "Right_Hip_Roll",
                "Right_Hip_Yaw",
                "Right_Knee_Pitch",
                "Right_Ankle_Pitch",
                "Right_Ankle_Roll"}},
        {"Booster-K1", {"AAHead_yaw",
                "Head_pitch",
                "ALeft_Shoulder_Pitch",
                "Left_Shoulder_Roll",
                "Left_Elbow_Pitch",
                "Left_Elbow_Yaw",
                "ARight_Shoulder_Pitch",
                "Right_Shoulder_Roll",
                "Right_Elbow_Pitch",
                "Right_Elbow_Yaw",
                "Left_Hip_Pitch",
                "Left_Hip_Roll",
                "Left_Hip_Yaw",
                "Left_Knee_Pitch",
                "Left_Ankle_Pitch",
                "Left_Ankle_Roll",
                "Right_Hip_Pitch",
                "Right_Hip_Roll",
                "Right_Hip_Yaw",
                "Right_Knee_Pitch",
                "Right_Ankle_Pitch",
                "Right_Ankle_Roll"}}
    };

std::string BridgeNode::getRobotType(const std::string& robot_name) {
    size_t firstUnderscore = robot_name.find('_');
    size_t secondUnderscore = robot_name.find('_', firstUnderscore + 1);
    if (firstUnderscore != std::string::npos && secondUnderscore != std::string::npos) {
        return robot_name.substr(firstUnderscore + 1, secondUnderscore - firstUnderscore - 1);
    }
    throw std::invalid_argument("ERROR: Robot name format is invalid: " + robot_name);
}

void BridgeNode::connectToServer_(const std::string& ip, int port) {
    client_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (client_fd < 0) {
        throw std::runtime_error("Failed to create socket");
    }

    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(port);

    if (inet_pton(AF_INET, ip.c_str(), &server_addr.sin_addr) <= 0) {
        throw std::runtime_error("Invalid address or address not supported");
    }

    if (connect(client_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        throw std::runtime_error("Connection to server failed");
    }

    setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &socket_recv_timeout, sizeof(socket_recv_timeout));

    RCLCPP_INFO(this->get_logger(), "Connected to server at %s:%d ", ip.c_str(), port);
    RCLCPP_INFO(this->get_logger(), "Sending initial message with robot name: %s", robotName_.c_str());

    msgpack::sbuffer sbuf;
    msgpack::pack(sbuf, robotName_);

    ssize_t sent = send(client_fd, sbuf.data(), sbuf.size(), 0);
    if (sent < 0) {
        throw std::runtime_error("Failed to send initial robot_name message");
    } else {
        RCLCPP_INFO(this->get_logger(), "Initial robot name sent successfully");
    }
}

void BridgeNode::jointCommandCallback(const sensor_msgs::msg::JointState::SharedPtr msg) {
    // DEBUG
    // RCLCPP_INFO(this->get_logger(), "Received Joint Commands with %zu joints.", msg->position.size());
    // for (size_t i = 0; i < msg->position.size(); i++) {
    //     std::cout << " joint_" << i << " = " << msg->effort[i] << std::endl;
    // }

    // RCLCPP_INFO(this->get_logger(), "Sending message to simulator.");
    sendMessageToSimulator_(msg);
}

void BridgeNode::sendMessageToSimulator_(const sensor_msgs::msg::JointState::SharedPtr message) {
    std::map<std::string, msgpack::object> data_map;
    msgpack::zone z;
    std::vector<double> effort = message->effort;
    data_map["robot_name"] = msgpack::object(robotName_, z);
    data_map["joint_torques"] = msgpack::object(effort, z);

    msgpack::sbuffer sbuf;
    msgpack::pack(sbuf, data_map);

    // RCLCPP_INFO(this->get_logger(), "Serialized message size: ", sbuf.size(), " bytes");

    ssize_t sent = send(client_fd, sbuf.data(), sbuf.size(), 0);
    if (sent < 0) {
        throw std::runtime_error("Failed to send message");
    }
    // RCLCPP_INFO(this->get_logger(), "Message sent! Check the simulator");
}

void BridgeNode::publishInitialMessagesWrapper() {
    // Ensure the timer runs only once
    init_timer_->cancel();

    // Publish initial messages
    RCLCPP_INFO(this->get_logger(), "Publishing initial JointState and IMU messages...");
    receiveAndPublish();
    RCLCPP_INFO(this->get_logger(), "Initial messages published (?)");

    periodic_timer_ = this->create_wall_timer(sim2frw_period, std::bind(&BridgeNode::receiveAndPublish, this));
}

void BridgeNode::receiveAndPublish() {
    // RCLCPP_INFO(this->get_logger(), "Receiving state from simulator");
    SimulatorNormalOutput simulator_msgs = receiveMessageFromSimulator_();
    publishSharedImages_();
    if (!simulator_msgs.ok) {
        return;
    }
    joint_state_pub_->publish(simulator_msgs.joint_state);
    imu_pub_->publish(simulator_msgs.imu);
    simbridge::msg::Odometer odometry_msg{};
    odometry_msg.x = 1;
    odometry_msg.y = 2;
    odometry_msg.theta = 0.5;
    odometer_pub_->publish(odometry_msg);
}

SimulatorNormalOutput BridgeNode::receiveMessageFromSimulator_() {
    std::vector<char> buffer(4096 * 2);

    ssize_t bytes_received = recv(client_fd, buffer.data(), buffer.size(), 0);
    if (bytes_received < 0) {
        if ((errno == EAGAIN) || (errno == EWOULDBLOCK)) {
            return {false, sensor_msgs::msg::JointState{}, sensor_msgs::msg::Imu{}};
        }
        throw std::runtime_error("Failed to receive message");
    }

    if (bytes_received == 0) {
        RCLCPP_INFO(this->get_logger(), "Connection closed by simulator");
        return {true, sensor_msgs::msg::JointState{}, sensor_msgs::msg::Imu{}};
    }

    try {
        // Unpack received message (usa il numero di byte ricevuti)
        msgpack::object_handle oh = msgpack::unpack(buffer.data(), static_cast<size_t>(bytes_received));
        msgpack::object obj = oh.get();

        std::map<std::string, msgpack::object> data_map = obj.as<std::map<std::string, msgpack::object>>();

        // Timestamp for headers
        auto now = std::chrono::system_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(now.time_since_epoch()).count();
        builtin_interfaces::msg::Time timestamp;
        timestamp.sec = static_cast<int32_t>(ns / 1000000000ULL);
        timestamp.nanosec = static_cast<uint32_t>(ns % 1000000000ULL);

        
        // Extract messages
        std::string robot_name = extractRobotName_(data_map);
        if (robot_name != robotName_) {
            std::cerr << "Warning: message must be for " << robotName_ << ", instead was for " << robot_name << std::endl;
            return {false, sensor_msgs::msg::JointState{}, sensor_msgs::msg::Imu{}};
        }

        sensor_msgs::msg::Imu imu_msg = extractImuData_(data_map, timestamp);
        sensor_msgs::msg::JointState joint_state_msg = extractJointStatesData_(data_map, timestamp, joint_names_);
        
        return {true, joint_state_msg, imu_msg};

    } catch (const std::exception& e) {
        std::cerr << "Error parsing message: " << e.what() << std::endl;
        return {false, sensor_msgs::msg::JointState{}, sensor_msgs::msg::Imu{}};
    }
}

std::string BridgeNode::shmFilePath_(const std::string& camera) const {
    return shm_dir_ + "/" + robotName_ + "_" + camera + ".shm";
}

void BridgeNode::publishSharedImages_() {

    ImageSharedMemoryReader::Frame left_frame{};
    if (left_image_reader_.readLatest(left_frame) && left_frame.channels == 3 && left_frame.width > 0 && left_frame.height > 0) {
        sensor_msgs::msg::Image left_msg{};
        left_msg.header.stamp = this->now();
        left_msg.header.frame_id = "booster_left_cam";
        left_msg.width = static_cast<uint32_t>(left_frame.width);
        left_msg.height = static_cast<uint32_t>(left_frame.height);
        left_msg.encoding = "rgb8";
        left_msg.is_bigendian = false;
        left_msg.step = static_cast<sensor_msgs::msg::Image::_step_type>(left_frame.width * left_frame.channels);
        left_msg.data = std::move(left_frame.data);
        camera_left_pub_->publish(left_msg);
    }

    ImageSharedMemoryReader::Frame right_frame{};
    if (right_image_reader_.readLatest(right_frame) && right_frame.channels == 3 && right_frame.width > 0 && right_frame.height > 0) {
        sensor_msgs::msg::Image right_msg{};
        right_msg.header.stamp = this->now();
        right_msg.header.frame_id = "booster_right_cam";
        right_msg.width = static_cast<uint32_t>(right_frame.width);
        right_msg.height = static_cast<uint32_t>(right_frame.height);
        right_msg.encoding = "rgb8";
        right_msg.is_bigendian = false;
        right_msg.step = static_cast<sensor_msgs::msg::Image::_step_type>(right_frame.width * right_frame.channels);
        right_msg.data = std::move(right_frame.data);
        camera_right_pub_->publish(right_msg);
    }
}
