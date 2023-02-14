#! /usr/bin/env python3
# -- coding: utf-8 --

"""
About: Simple client.
"""

import socket
import time

SERVICE_IP = "10.0.0.123"
SERVICE_PORT = 8888

if __name__ == "__main__":
    # Declare that will use IP/UDP protocols
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Wait for the answer for 2 seconds
    sock.settimeout(2)
    data = b"Show me the counter, please!" # msg sent to server

    while True:
        # Sends packet to server
        print(" Sending data...")
        sock.sendto(data, (SERVICE_IP, SERVICE_PORT))
        try:
            # Wait for the answer from server
            counter, _ = sock.recvfrom(1024)
            print("Client received: <{}>".format(counter.decode("utf-8")))
            time.sleep(1)
        except socket.timeout: 
            # If does not receive answer, wait 5 seconds
            print("Client received: <nothing>")
            time.sleep(5)
            pass
        