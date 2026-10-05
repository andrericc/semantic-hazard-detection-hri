# Framework-Simulator Bridge
This is the bridge that allows the communication of our simulator **Circus** with our framework **Maximus**.
It is mainly used inside the dockers representing the robots.

## How to compile
Install the pixi environment:
```
pixi install
```
To compile:
```
pixi run build
```
If you want to clean the build folder:
```
pixi run clean
```

## How to execute the program
If you have to use it **INSIDE** the docker, you don't need to execute it manually, you just need to compile it. The execution happens automatically inside the docker.

If you want to use it **OUTSIDE** the docker, you have to export the following environment variables on the terminal where you will execute the bridge:
```
export ROBOT_NAME=<robot_name>
export SERVER_IP=<server_ip>
export CIRCUS_PORT=<circus_port>
```
where the `<robot_name>` is the name of the robot to be connected to the simualtor, `<server_ip>` is the ip address where the simulator (Circus) is executed (if you run the bridge outside the docker probably is `127.0.0.1`), `<circus_port>` is the port where the simulator communicates (probably `5555`).
After this, to run the program:
```
pixi run simbridge
```
