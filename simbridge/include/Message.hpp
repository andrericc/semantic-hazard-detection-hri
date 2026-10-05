#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "sensor_msgs/msg/joint_state.hpp"

struct SimulatorNormalOutput {
    bool ok;
    sensor_msgs::msg::JointState joint_state;
    sensor_msgs::msg::Imu imu;
};

// TODO: Questo file potrebbe contenere tutte le possibili struct di messaggi scambiati con il simulatore.
// Questo permetterebbe di avere facilmente lo switch da modalità normale a Fast (con l'oracolo).
// Ad esempio, si può fare una struct OracleReceiveOutput che riceve i messaggi quando la scena di circus è
// fast (e quindi contiene anche i campi sulla palla, sugli avversari, sulla porta, ....), mentre le scene
// normali dovrebbero contenere solo le immagini (e ricavare le altre informazioni da quelle).
// 
// Una volta che ci sono le struct ReceiveOutput e OracleReceiveOutput (e rispettivamente le funzioni
// receiveMessageFromSimulator_
//  e OracleReceiveMessageFromSimulator_), la funzione receiveAndPublish controlla quale modalità è attiva
//  (normale o Fast)
// e chiama la funzione giusta per ricevere i messaggi dal simulatore.
// Le funzioni receiveMessageFromSimulator_, OracleReceiveMessageFromSimulator_ ed eventuali altre, vanno messe in 
// bridge_node perché gestiscono le socket, quindi sono direttamente legate al nodo ros.
// 
// Il flag ORACLE_MODE potrebbe essere definito all'interno del file yaml della scena, e nel SceneParser viene
// letto come campo (così il simulatore sa quale modalità eseguire e quindi quali messaggi mandare via
// socket). Questo campo viene usato per settare una variabile d'ambiente quando vengono lanciati i container
// In questo modo, tutte le componenti nel docker (framework, simbridge) sono a conoscenza della modalità in
// uso, e possono agire in maniera differente
// 
// BONUS:
// La stessa logica si potrebbe attuare per i messaggi di comando inviati (se magari qualcuno volesse mandare comandi diversi,
// oppure se volesse mandare ulteriori informazioni). Al momento non mi viene in mente il motivo, quindi sarà per dopo


inline std::string extractRobotName_(const std::map<std::string, msgpack::object>& data_map) {
    std::string robot_name{};
    auto robot_name_it = data_map.find("robot_name");
    if (robot_name_it != data_map.end()) {
        robot_name = robot_name_it->second.as<std::string>();
        // DEBUG
        std::cout << "Robot name: " << robot_name << std::endl;
    }    
    return robot_name;
}

inline sensor_msgs::msg::Imu extractImuData_(const std::map<std::string, msgpack::object>& data_map, builtin_interfaces::msg::Time& timestamp) {
    sensor_msgs::msg::Imu imu_msg{};

    // -----------  Imu Header
    imu_msg.header.stamp = timestamp;
    imu_msg.header.frame_id = "imu";

    // -----------  Imu Orientation (Pose from simulator)
    auto pose_it = data_map.find("pose");
    if (pose_it != data_map.end()) {
        std::map<std::string, msgpack::object> pose_data
            = pose_it->second.as<std::map<std::string, msgpack::object>>();

        // -----------  Imu Quaternion Orientation
        auto orientation_it = pose_data.find("quat_orientation");
        if (orientation_it != pose_data.end()) {
            std::vector<double> orientation = orientation_it->second.as<std::vector<double>>();
            if (orientation.size() == 4) {
                // order from simulator [w, x, y, z]; if it is different, invert here
                imu_msg.orientation.w = orientation[0];
                imu_msg.orientation.x = orientation[1];
                imu_msg.orientation.y = orientation[2];
                imu_msg.orientation.z = orientation[3];
            } else {
                std::cerr << "Warning: pose.orientation size != 4 (" << orientation.size() << ")\n";
            }

            // // DEBUG
            // std::cout << "Orientation: [";
            // for (size_t i = 0; i < orientation.size(); ++i) {
            //     std::cout << orientation[i];
            //     if (i + 1 < orientation.size())
            //         std::cout << ", ";
            // }
            // std::cout << "]\n";
        }
    }
    // -----------  Imu data (Imu from simulator)
    auto imu_it = data_map.find("imu");
    if (imu_it != data_map.end()) {
        std::map<std::string, msgpack::object> imu_data
            = imu_it->second.as<std::map<std::string, msgpack::object>>();

        // -----------  Imu Linear Acceleration
        auto linear_acc_it = imu_data.find("linear_acceleration");
        if (linear_acc_it != imu_data.end()) {
            std::vector<double> linear_acceleration = linear_acc_it->second.as<std::vector<double>>();
            if (linear_acceleration.size() == 3) {
                imu_msg.linear_acceleration.x = linear_acceleration[0];
                imu_msg.linear_acceleration.y = linear_acceleration[1];
                imu_msg.linear_acceleration.z = linear_acceleration[2];
            } else {
                std::cerr << "Warning: imu.linear_acceleration size != 3 (" << linear_acceleration.size()
                            << ")\n";
            }
        }

        // -----------  Imu Angular Velocity
        auto angular_vel_it = imu_data.find("angular_velocity");
        if (angular_vel_it != imu_data.end()) {
            std::vector<double> angular_velocity = angular_vel_it->second.as<std::vector<double>>();
            if (angular_velocity.size() >= 3) {
                imu_msg.angular_velocity.x = angular_velocity[0];
                imu_msg.angular_velocity.y = angular_velocity[1];
                imu_msg.angular_velocity.z = angular_velocity[2];
            } else {
                std::cerr << "Warning: imu.angular_velocity size < 3 (" << angular_velocity.size()
                            << ")\n";
            }

            // // DEBUG
            // std::cout << "Angular Velocity: [";
            // for (size_t i = 0; i < angular_velocity.size(); ++i) {
            //     std::cout << angular_velocity[i];
            //     if (i + 1 < angular_velocity.size())
            //         std::cout << ", ";
            // }
            // std::cout << "]\n";
        }
    }

    // Covariances set to zero because UNKNOWN.
    // When they will be known, change here
    for (int i = 0; i < 9; i++) {
        imu_msg.orientation_covariance[i] = 0.0;
        imu_msg.angular_velocity_covariance[i] = 0.0;
        imu_msg.linear_acceleration_covariance[i] = 0.0;
    }

    return imu_msg;
}

inline sensor_msgs::msg::JointState extractJointStatesData_(const std::map<std::string, msgpack::object>& data_map, const builtin_interfaces::msg::Time& timestamp, const std::vector<std::string> joint_names) {
    sensor_msgs::msg::JointState joint_state_msg{};

    auto joints_it = data_map.find("joints");
    if (joints_it != data_map.end()) {
        std::map<std::string, msgpack::object> joints_data
            = joints_it->second.as<std::map<std::string, msgpack::object>>();

        // -----------  Joint Header
        joint_state_msg.header.stamp = timestamp;
        joint_state_msg.header.frame_id = "base_link";

        // -----------  Names
        joint_state_msg.name = joint_names;
        // // DEBUG
        // std::cout << "Joints Names: [";
        // for (size_t i = 0; i < joint_names.size(); ++i) {
        //     std::cout << joint_names[i];
        //     if (i + 1 < joint_names.size())
        //         std::cout << ", ";
        // }
        // std::cout << "]\n";

        // -----------  Positions
        auto joints_position_it = joints_data.find("position");
        if (joints_position_it != joints_data.end()) {
            std::vector<double> joints_position = joints_position_it->second.as<std::vector<double>>();
            joint_state_msg.position = joints_position;

            // DEBUG
            // std::cout << "Joints Position: [";
            // for (size_t i = 0; i < joints_position.size(); ++i) {
            //     std::cout << joints_position[i];
            //     if (i + 1 < joints_position.size())
            //         std::cout << ", ";
            // }
            // std::cout << "]\n";
        }

        // -----------  Velocities
        auto joints_velocity_it = joints_data.find("velocity");
        if (joints_velocity_it != joints_data.end()) {
            std::vector<double> joints_velocity = joints_velocity_it->second.as<std::vector<double>>();
            joint_state_msg.velocity = joints_velocity;

            // // DEBUG
            // std::cout << "Joints Velocity: [";
            // for (size_t i = 0; i < joints_velocity.size(); ++i) {
            //     std::cout << joints_velocity[i];
            //     if (i + 1 < joints_velocity.size())
            //         std::cout << ", ";
            // }
            // std::cout << "]\n";
        }

        // -----------  Efforts / Torques
        auto joints_effort_it = joints_data.find("torque");
        if (joints_effort_it != joints_data.end()) {
            std::vector<double> joints_effort = joints_effort_it->second.as<std::vector<double>>();
            joint_state_msg.effort = joints_effort;

            // // DEBUG
            // std::cout << "Joints Effort: [";
            // for (size_t i = 0; i < joints_effort.size(); ++i) {
            //     std::cout << joints_effort[i];
            //     if (i + 1 < joints_effort.size())
            //         std::cout << ", ";
            // }
            // std::cout << "]\n";
        }
    }

    return joint_state_msg;
}
