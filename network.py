#!/usr/bin/python3
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from time import sleep
from comnetsemu.net import Containernet, VNFManager  
from mininet.log import info, setLogLevel
import re 
from topology import topo 
import random 

CONTROLLER_IP = "127.0.0.1"

if __name__ == "__main__":
    #setLogLevel("debug")
    net = Containernet(
        switch=OVSKernelSwitch,
        build=False,
        autoSetMacs=True,
        autoStaticArp=False,
        xterms=False,
        link=TCLink
    )
    manager = VNFManager(net)
    # Add switch controller to the network
    controller = RemoteController("c1", ip=CONTROLLER_IP, port=6633)
    net.addController(controller)

    # Counting numbers of switches, servers and hosts
    nswitches = len([x for x in topo if "switch" in x])
    nhosts = len([x for x in topo if "host" in x])
    nservers = len([x for x in topo if "server" in x])
    print(nswitches, nhosts, nservers)

    # Create switch nodes
    switches = []
    for i in range(nswitches):
        sconfig = {"dpid": "%016x" % (i + 1)}
        switches.append(net.addSwitch("switch{}".format(i + 1), **sconfig))

    # Create hosts
    # Containers here are used only as base for hosts 
    hosts = []
    for i in range(nhosts):
        hosts.append(net.addDockerHost(
            name="host{}".format(i+1), dimage="dev_test", ip="10.0.0.{}/24".format(i+11),
            docker_args={"hostname": "host{}".format(i+1)}))
    # IP pool of hosts = 10.0.0.11-20/24
    
    # Create server hosts
    # Containers here are used only as base for hosts 
    servers = []
    for i in range(nservers):
        servers.append(net.addDockerHost(
            name="server{}".format(i+1), dimage="dev_test", wait=False,
            docker_args={"hostname": "server{}".format(i+1)}))    

    # Takes all nodes in the same place
    nodes = {}
    for h in hosts:
        nodes[h.name] = h 
    for h in switches:
        nodes[h.name] = h 
    for h in servers:
        nodes[h.name] = h 
    

    # Specify the performance of the links
    host_config = dict(inNamespace=True, bw=10, delay="5ms")
    switch_config = dict(inNamespace=True, bw=20, delay="5ms")
    server_config = dict(inNamespace=True, bw=50, delay="5ms")

    # Add named links 
    for node in topo:
        for adj in topo[node]:
            # Regex retrieves the type of node and its index
            tipo, num = re.findall(r"^([a-zA-Z]+)(\d+)$", node)[0]
            # For example: "switch1" => type="switch" , num=1
            num = int(num) - 1

            # Add link and interfaces on both sides 
            if tipo == "host":
                net.addLinkNamedIfce(hosts[num], nodes[adj], **host_config)
            elif tipo == "server":
                net.addLinkNamedIfce(servers[num], nodes[adj], **server_config)
            elif tipo == "switch":
                net.addLinkNamedIfce(switches[num], nodes[adj], **switch_config)
            else:
                print("Error: the node of this type ({}) is not supported".format(tipo))
                exit(2)

    net.build()
    
    # Change MAC addresses of servers
    for server in servers:
        for intf in server.intfList():
            server.setMAC("00:00:00:cc:00:00", intf)

    net.start()
    
    # Eventually (DEBUG) Change MAC addresses of hosts
    #hosts = ["host{}".format(i+1) for i in range(7)]
    #for (i, host) in enumerate(hosts):
    #    host1 = net.getNodeByName(host)
    #    for (j, intf) in enumerate(host1.intfList()):
    #        host1.setMAC("00:00:00:aa:0{}:0{}".format(i+1, j+1), intf)
    #        print("00:00:00:aa:0{}:0{}".format(i+1, j+1))

    print("Starting servers...", end="")

    counter_servers = []
    # Set the first server as active (without --get_state)
    counter_servers.append(
        manager.addContainer(
            "counter_server1", "server1", "service_migration", 
            dcmd="python /home/server.py server1",
            docker_args = {'privileged': True}
        )) # privileged because the server need to create namespaces
    # Set all other servers as inactive
    for (i, svr) in enumerate(servers[1:]):
        counter_servers.append(
            manager.addContainer(
                "counter_server{}".format(i+2), svr.name, "service_migration",
                dcmd="python /home/server.py --get_state  server{}".format(i+2),
                docker_args = {'privileged': True}
            ))

    print("Done")

    # Add randomly clients
    clients = []
    occupied = []
    nclients = random.randint(2, len(hosts))
    for i in range(nclients):
        h = random.choice(hosts)
        if h.name not in occupied:
            occupied.append(h.name)
            clients.append(
                manager.addContainer(
                    "client_{}".format(h.name), h.name, "service_migration", 
                    dcmd="python /home/client.py"
                )
            )
            sleep(5)
    
    # DEBUG: logs of servers
    # sleep(50)
    # print(counter_server1.getLogs())
    # print(client1.getLogs())
    # print(client2.getLogs())
    
    CLI(net)

    # server1 ip netns exec net0 ping -c1 host1
    # Ping host1 from server1

    # Delete all containers
    for svr in servers:
        containers = manager.getAllContainers()
        for c in containers:
            manager.removeContainer(c)

    net.stop()
