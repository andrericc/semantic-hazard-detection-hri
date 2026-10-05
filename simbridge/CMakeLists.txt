# ================== PROJECT SETUP ===================
cmake_minimum_required(VERSION 3.22)
project(simbridge VERSION 0.1 LANGUAGES C CXX)
set(LIBRARY simbridge_lib)

# Set C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -Wpedantic")
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Generate .clangd config for LSP
file(
    WRITE "${CMAKE_CURRENT_SOURCE_DIR}/.clangd"
    "CompileFlags:
  CompilationDatabase: ${CMAKE_CURRENT_BINARY_DIR}
"
)

add_compile_definitions(PROJECT_ROOT="${CMAKE_SOURCE_DIR}")
# ====================================================

# ================ ROS2 Dependencies =================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
# ====================================================

# ================ Generate ROS2 Messages ============
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/RpcReqMsg.msg"
  "msg/BoosterApiRespMsg.msg"
  "msg/ButtonEventMsg.msg"
  "msg/MotorState.msg"
  "msg/MotorCmd.msg"
  "msg/LowCmd.msg"
  "msg/ImuState.msg"
  "msg/LowState.msg"
  "msg/RawBytesMsg.msg"
  "msg/Odometer.msg"
  "msg/FallDownState.msg"
  "msg/RemoteControllerState.msg"
  "msg/HandCommand.msg"
  "msg/HandDdsMsg.msg"
  "msg/HandParam.msg"
  "msg/HandActionStatus.msg"
  "msg/ProneBodyControlStatus.msg"
  "msg/RobotStatesMsg.msg"
  "msg/RobotReplayTrajID.msg"
  "msg/Subtitle.msg"
)
# ====================================================

# ================== MESSAGES LIBRARY ================
# Create an INTERFACE library that exposes the generated messages
add_library(${LIBRARY} INTERFACE)

# Get the typesupport target for our generated messages
rosidl_get_typesupport_target(cpp_typesupport_target
    ${PROJECT_NAME} "rosidl_typesupport_cpp"
)

# Link dependencies — these will be transitive to downstream packages
target_link_libraries(
    ${LIBRARY}
    INTERFACE
        "${cpp_typesupport_target}"
        nlohmann_json::nlohmann_json
)
# ====================================================

# ================ EXECUTABLE ========================
add_executable(${PROJECT_NAME}_node
    src/main.cpp
    src/bridge_node.cpp
)

add_dependencies(${PROJECT_NAME}_node ${PROJECT_NAME})


# IMPORTANT: Call rosidl_target_interfaces FIRST (uses plain signature)
rosidl_target_interfaces(${PROJECT_NAME}_node
    ${PROJECT_NAME} "rosidl_typesupport_cpp"
)

# THEN use target_link_libraries with plain signature to match
target_link_libraries(${PROJECT_NAME}_node
    ${LIBRARY}
    rclcpp::rclcpp
    sensor_msgs::sensor_msgs__rosidl_typesupport_cpp
)

# Add include directories for the executable
target_include_directories(${PROJECT_NAME}_node
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Install the executable
install(TARGETS ${PROJECT_NAME}_node
    RUNTIME DESTINATION lib/${PROJECT_NAME}
    RUNTIME DESTINATION bin/
)
# ====================================================

# ================ INSTALL LIBRARY ===================
install(
    TARGETS ${LIBRARY}
    EXPORT ${PROJECT_NAME}Targets
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION lib
)

install(
    EXPORT ${PROJECT_NAME}Targets
    FILE ${PROJECT_NAME}Targets.cmake
    NAMESPACE simbridge::
    DESTINATION lib/cmake/${PROJECT_NAME}
)

include(CMakePackageConfigHelpers)

# Config file — declare all public (transitive) dependencies
set(CONFIG_CONTENT "include(CMakeFindDependencyMacro)\n")
string(APPEND CONFIG_CONTENT "find_dependency(rclcpp REQUIRED)\n")
string(APPEND CONFIG_CONTENT "find_dependency(rosidl_default_runtime REQUIRED)\n")
string(APPEND CONFIG_CONTENT "find_dependency(nlohmann_json REQUIRED)\n")
string(
    APPEND CONFIG_CONTENT
    "include(\"\${CMAKE_CURRENT_LIST_DIR}/${PROJECT_NAME}Targets.cmake\")\n"
)
file(
    WRITE "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake"
    "${CONFIG_CONTENT}"
)

write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(
    FILES
        "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake"
    DESTINATION lib/cmake/${PROJECT_NAME}
)
# ====================================================

# ================ Export for ament ==================
ament_export_targets(${PROJECT_NAME}Targets HAS_LIBRARY_TARGET)
ament_export_dependencies(
    rclcpp
    rosidl_default_runtime
    nlohmann_json
)

ament_package()
# ====================================================

message(STATUS "simbridge configured successfully")
message(STATUS "  C++ Standard: ${CMAKE_CXX_STANDARD}")