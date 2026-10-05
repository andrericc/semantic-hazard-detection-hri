#include "bridge_node.hpp"

int main(int argc, char** argv) {
    const char* robotName = std::getenv("ROBOT_NAME");
    const char* serverIp = std::getenv("SERVER_IP");
    const char* circus_port = std::getenv("CIRCUS_PORT");

    std::cout << "Robot name:   " << robotName << std::endl;
    std::cout << "Server ip:   " << serverIp << std::endl;

    if (!robotName) {
        throw std::runtime_error("Environment variable ROBOT_NAME is not set");
    }
    if (!serverIp) {
        throw std::runtime_error("Environment variable SERVER_IP is not set");
    }

    std::string robotNameStr(robotName);
    std::string serverIpStr(serverIp);
    int circusPort = circus_port ? std::stoi(circus_port) : 5555;

    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<BridgeNode>(robotNameStr, serverIpStr, circusPort));
    rclcpp::shutdown();
    return 0;
}
