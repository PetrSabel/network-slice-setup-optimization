import random

topo = {}

answer = input("Choose: 1) Use example network\n2) Create a random network\n")
if answer == "2":
    while True:
        nhost = input("Insert number of hosts (between 2 and 9): ")
        try:
            nhost = int(nhost)
            if nhost < 2:
                print("Number must be higher than 1")
            elif nhost > 9:
                print("Number is too big")
            else:
                break
        except:
            print("Insered value is not a number")

    while True:
        nswitch = input("Insert number of switches (between 2 and 9): ")
        try:
            nswitch = int(nswitch)
            if nswitch < 2:
                print("Number must be higher than 1")
            elif nswitch > 9:
                print("Number is too big")
            else: 
                break
        except:
            print("Insered value is not a number")


    while True:
        nservers = input("Insert number of servers (between 2 and 9): ")
        try:
            nservers = int(nservers)
            if nservers < 2:
                print("Number must be at least 2 (to permit migration)")
            elif nservers > 9:
                print("Number is too big")
            else: 
                break
        except:
            print("Inserted value is not a number")
        
            

    print("Servers: {}\nHosts: {}\nSwitches: {}".format(nservers, nhost, nswitch))
    
    switches = []
    for i in range(1, nswitch+1):
        switches.append("switch{}".format(i))

    random.shuffle(switches)

    hosts = []
    for i in range(1, nhost+1):
        h = "host{}".format(i)
        hosts.append(h)
        # Choose casually switch to connect
        sw = random.choice(switches)
        topo[h] = [sw]

    servers = []
    for i in range(1, nservers+1):
        svr = "server{}".format(i)
        servers.append(svr)
        # Choose casually switch to connect
        sw = random.choice(switches)
        topo[svr] = [sw] 

    visited = [switches[0]]
    topo.setdefault(switches[0], [])
    if len(switches) > 1:
        topo[switches[1]] = [switches[0]]
        visited.append(switches[1])
    # Skip 2 first switches
    for sw in switches[2:]:
        nlinks = random.randint(1, len(visited))
        topo.setdefault(sw, [])
        for i in range(nlinks):
            s = random.choice(visited)
            if s not in topo[sw]:
                topo[sw].append(s)

    print("Created topology")
    print(topo)

elif answer == "1":
    topo["host1"] = ["switch1"]
    topo["host2"] = ["switch2"]
    topo["host3"] = ["switch4"] 
    topo["host4"] = ["switch5"] 
    topo["host5"] = ["switch7"] 
    topo["host6"] = ["switch7"] 
    topo["host7"] = ["switch6"] 
    topo["server1"] = ["switch1"]
    topo["server2"] = ["switch2", "switch4"] 
    topo["server3"] = ["switch6", "switch3"] 
    topo["switch1"] = ["switch2", "switch3", "switch4"]
    topo["switch2"] = ["switch4"] 
    topo["switch3"] = ["switch8"] 
    topo["switch4"] = ["switch3"] 
    topo["switch5"] = ["switch3","switch4"] 
    topo["switch6"] = ["switch3"]
    topo["switch7"] = ["switch6", "switch1"] 
    topo["switch8"] = ["switch6"] 
    print("Created default topology")
    print(topo)
else: 
    print("Choose 1 or 2")


    
