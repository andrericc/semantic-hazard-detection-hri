#include <arpa/inet.h>
#include <netinet/in.h>
#include <unistd.h>

#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <memory>
#include <msgpack.hpp>
#include <stdexcept>
#include <string>
#include <vector>

#include "ImageSharedMemoryReader.hpp"
#include "Message.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "simbridge/msg/odometer.hpp"

using namespace std::chrono_literals;

class BridgeNode : public rclcpp::Node {
   public:
    BridgeNode(const std::string& robotName, const std::string& serverIp, int serverPort)
        : Node("bridge_node"), robotName_(robotName) {

        std::string robot_type = getRobotType(robotName_);
        if (ROBOT_JOINTS_NAMES_MAP.find(robot_type) != ROBOT_JOINTS_NAMES_MAP.end()) {
            joint_names_ = ROBOT_JOINTS_NAMES_MAP.at(robot_type); 
        } else {
            throw std::runtime_error("Robot type not found in the map: " + robot_type);
        }
        // ---- Subscriber: Joint Command (Torques) ----
        joint_cmd_sub_ = this->create_subscription<sensor_msgs::msg::JointState>(
            "/booster/ros2_k2_joint_cmd", 10,
            std::bind(&BridgeNode::jointCommandCallback, this, std::placeholders::_1));

        // ---- Publisher: Joint States  ----
        joint_state_pub_
            = this->create_publisher<sensor_msgs::msg::JointState>("/booster/ros2_k2_joint_states", 10);

        // ---- Publisher: IMU  ----
        imu_pub_ = this->create_publisher<sensor_msgs::msg::Imu>("/booster/ros2_k2_imu", 10);

        // ---- Publisher: Cameras ----
        camera_left_pub_ = this->create_publisher<sensor_msgs::msg::Image>("/booster/camera/left/image_raw", 10);
        camera_right_pub_ = this->create_publisher<sensor_msgs::msg::Image>("/booster/camera/right/image_raw", 10);

        // ---- Publisher: Odometer  ----
        odometer_pub_ = this->create_publisher<simbridge::msg::Odometer>("simbridge/odometry", 10);


        shm_dir_ =  "/tmp/circus_ipc";
        left_image_reader_.configure(shmFilePath_("left"));
        right_image_reader_.configure(shmFilePath_("right"));
    

        // Connect to simulator server
        connectToServer_(serverIp, serverPort);

        // Timer to publish initial messages once node starts.
        // It is necessary due to the initialization of booster-motion
        init_timer_
            = this->create_wall_timer(0ms, std::bind(&BridgeNode::publishInitialMessagesWrapper, this));

        RCLCPP_INFO(this->get_logger(), "BridgeNode initialized.");
        
    }
   private:
    std::string getRobotType(const std::string& robot_name);
    
    // Subscriber callback
    void jointCommandCallback(const sensor_msgs::msg::JointState::SharedPtr msg);

    // Publish initial messages
    void receiveAndPublish();
    void publishInitialMessagesWrapper();

    void connectToServer_(const std::string& ip, int port);
    void sendMessageToSimulator_(const sensor_msgs::msg::JointState::SharedPtr message);
    SimulatorNormalOutput receiveMessageFromSimulator_();
    void publishSharedImages_();
    std::string shmFilePath_(const std::string& camera) const;

    // ROS interfaces
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_cmd_sub_;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr camera_left_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr camera_right_pub_;
    rclcpp::Publisher<simbridge::msg::Odometer>::SharedPtr odometer_pub_;
    rclcpp::TimerBase::SharedPtr init_timer_;
    rclcpp::TimerBase::SharedPtr periodic_timer_;

    // The following timespans must be equal. If less than 1us is needed,
    // then the socket+timeout paradigm might not be feasible anymore.
    // In that case, maybe switch to a select-based one?
    const struct timeval socket_recv_timeout{0, 1};
    const std::chrono::microseconds sim2frw_period = 1us;

    int client_fd = -1;
    std::string robotName_;
    std::string shm_dir_;
    ImageSharedMemoryReader left_image_reader_;
    ImageSharedMemoryReader right_image_reader_;

    std::vector<std::string> joint_names_;

    static const std::map<std::string, std::vector<std::string>> ROBOT_JOINTS_NAMES_MAP;
};
