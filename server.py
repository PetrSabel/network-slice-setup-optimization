#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
About: Simple server for counting.
"""

import argparse
import socket
import time
import threading 
import os, signal
from pyroute2 import netns, NetNS, IPRoute
import sys 


STOP_EVENT = threading.Event()
INTERNAL_IP = "192.168.0." # +hostname
INTERNAL_PORT = 9999
MIGRATE_PORT = 8899

SERVICE_IP = "10.0.0.123"
SERVICE_PORT = 8888
counter = 0
MANTAIN_STATE = True 

def signal_handler(sig, frame):
    if sig == signal.SIGCHLD:
        #print("SIGCHILD STRANGE")
        return 

    if sig == signal.SIGUSR2:
        print("Migration in progress...")
    if not (threading.current_thread() is threading.main_thread()) :
        sys.exit(0) 

    STOP_EVENT.set()
    while threading.active_count() > 1:
        time.sleep(0.1)
    
    STOP_EVENT.clear()
    global MANTAIN_STATE
    MANTAIN_STATE = False 
    if sig == signal.SIGUSR1:
        print("Activating server...")
    elif sig == signal.SIGUSR2:
        print("Migrating server...")


def update():
    global counter 
    counter += 1

def getCounter():
    global counter
    return counter

def setCounter(x):
    global counter
    counter = x

# TODO: unite with recv_state_thread
def recv_state(namespace):
    """Get the latest counter state from the internal
    network.
    """

    netns.setns(namespace)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((INTERNAL_IP, INTERNAL_PORT))
    sock.settimeout(0.5)
    
    # Waiting for state
    print("Listening on internal port for state")
    
    # While the state is not received
    while not STOP_EVENT.is_set():
        try:
            state, _ = sock.recvfrom(1024)
            state = int(state.decode("utf-8"))
            sock.close()
            time.sleep(1)

            return state
        except socket.timeout:
            pass 
    
    sock.close()
    sys.exit(0)

def recv_state_thread(namespace):
    print("Listening for state in namespace <{}>".format(namespace))
    setCounter(recv_state(namespace))
    print("Received counter from old server: <{}>".format(getCounter()))
    os.kill(os.getpid(), signal.SIGUSR1)

def inactive():
    for ns in netns.listnetns():
        y = threading.Thread(target=recv_state_thread, args=(ns,), daemon=True)
        y.start()
    

def service(namespace): # crea il socket che ascolta i messaggi che arrivano al service ip nella porta service port
    netns.setns(namespace)
    print("Listening on IP: <{}>, port: <{}>".format(SERVICE_IP, SERVICE_PORT))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVICE_IP, SERVICE_PORT))
    sock.settimeout(0.5)

    while not STOP_EVENT.is_set():
        # Block here waiting for data input.
        try:
            msg, addr = sock.recvfrom(1024)
            update()
            sock.sendto(str(getCounter()).encode("utf-8"), addr)
            time.sleep(0.5)
            print("Counter <{}> is sent to IP,port: <{}>".format(getCounter(), addr))
        except socket.timeout:
            pass

def internal(namespace):    # aspetta richiesta di migrazione
    print("Waiting migration request in namespace <{}>".format(namespace))
    netns.setns(namespace)
    internal_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    internal_sock.bind((INTERNAL_IP, MIGRATE_PORT)) #TODO: change internal port to migrate port
    internal_sock.settimeout(0.5)

    while not STOP_EVENT.is_set():
        try:
            msg, addr = internal_sock.recvfrom(1024)
            # Migrate
            print("State request from IP,port <{}> in namespace <{}>".format(addr, namespace))
            print("Sleeping while network is configuring...")
            for _ in range(2):
                internal_sock.sendto(str(getCounter()).encode("utf-8"), (addr[0], INTERNAL_PORT))
                time.sleep(1)
            internal_sock.close()
            print("State sended to IP,port <{}>".format(addr))
            os.kill(os.getpid(), signal.SIGUSR2) # became inactive
            sys.exit(0)
        except socket.timeout:
            pass 
    internal_sock.close()
    
def active():
    for ns in netns.listnetns(): # for each namespace
        x = threading.Thread(target=service, args=(ns,), daemon=True) 
        # after being created execute function specified by target
        x.start()

        y = threading.Thread(target=internal, args=(ns,), daemon=True)
        y.start()        


def run(host_name, get_state=False):
    # Assign internal IP address for server
    """Run the counting service and handle sigterm signal."""
    print("Server <{}> has started".format(host_name))

    signal.signal(signal.SIGUSR1, signal_handler) #handler set
    signal.signal(signal.SIGUSR2, signal_handler)
    signal.signal(signal.SIGCHLD, signal_handler)
    STOP_EVENT.clear()

    # The first interface is loopback, the last one is unintended
    intfs = socket.if_nameindex()[1:-1]
    print(intfs)

    ipr = IPRoute() #is a library that handles the network interfaces
    #for i in ipr.get_links():
    #    print(i['attrs'][0][1])
    # TOO much info

    for (i, intf) in intfs:
        # Create net namespace for every interface
        # Because the interfaces will have the same IP and MAC addresses
        ns_name = "net{}".format(i)
        ns = NetNS(ns_name)
        
        # Move interface into dedicated namespace
        ipr.link('set', index=i, net_ns_fd=ns_name)
        dev = ns.link_lookup(ifname=intf)[0]
        ns.link('set', index=dev, state="up")
        # Add IP addresses to interface
        ns.addr('add', index=dev, address=SERVICE_IP, mask=24, broadcast='10.0.0.255') # Public
        ns.addr('add', index=dev, address=INTERNAL_IP, mask=24, broadcast='192.168.0.255') # Private

    while True:
        if get_state:
            inactive()
            get_state = False
        else: 
            active()
            get_state = True 
        global MANTAIN_STATE
        MANTAIN_STATE = True
        time.sleep(2)
        while MANTAIN_STATE:
            try:
                time.sleep(10)
            except Exception as e:
                print("{} Finished for some reason".format(threading.current_thread()))
                print(e)
    
    
        
            
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple counting server.")
    parser.add_argument(
        "hostname",
        type=str,
        help="The name of the host on which the server is deployed.",
    )
    parser.add_argument(
        "--get_state", action="store_true" , help="Get state from network."
    )
    
    args = parser.parse_args()
    # Skip "server" in hostname
    INTERNAL_IP += args.hostname[6:]
    # Internal servers IP = 192.168.0.1-9/24
    print("Server launched with IP = " + INTERNAL_IP)
    counter = 0

    run(args.hostname, args.get_state)
