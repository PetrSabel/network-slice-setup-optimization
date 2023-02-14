# Network Slice Setup Optimization
Example project of how RYU-controller can be used to perform the network slicing and possible server migration.

## Setup
Install the [ComNetsEmu](https://www.granelli-lab.org/researches/relevant-projects/comnetsemu-labs) virtual machine.
Launch the terminal of ComNetsEmu, copy the files of the project and execute the following commands.
Launch the RYU controller.
```bash
chmod +x build.sh
./build.sh
```
On the other terminal execute the following command:
```bash
sudo python3 network.py
```
It will launch the choice of the topology and the Mininet script.

## Logs
To see logs of the "server1":
```bash
sudo docker logs counter_server1
```
To see logs of the client launched on the host5:
```bash
sudo docker logs client_host5
```
To see all launched containers run:
```bash
sudo docker ps -a
```

## Terminate
```
mininet> exit
```
Ctrl-C for RYU controller

Note: please exit from mininet before relaunching the script *build.sh* because it can cause problem

## Predefined topology
image

## Example 

## Authors
- Dao Simone
- Grilli Filippo
- Sabel Petr

## Presentation
