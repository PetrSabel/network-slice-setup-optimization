from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3 
import time 
from ryu.ofproto import ether
from ryu.lib.packet import ethernet, ipv4, packet, udp

SERVICE_IP = "10.0.0.123" 
SERVICE_PORT = "8888" 
CLIENT_PRIORITY = 2
SERVER_PRIORITY = 3
MIGRATION_PORT = 8899

class Slicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    
    def __init__(self, *args, **kwargs):
        super(Slicing, self).__init__(*args, **kwargs)
        # initialize mac address table
        self.mac_to_port = {} # dpid -> MAC -> port_no
        self.curr_server = 'server1'
        self.clients = [] # ['host2', 'host3', 'host4', 'host5']
        self.links = {} # dpid -> hostname -> port_no
        self.server_links = {} # server -> datapath -> [port_no]
        self.datapaths = {} # dpid -> datapath Object
        self.open_ports = {} # dpid -> set{port_no ...}
        self.servers = [] 

    def delete_flows(self):
        # Delete old flows (with priority 3, 2 and 1)
        for dpid in self.datapaths:
            datapath = self.datapaths[dpid]
            parser = datapath.ofproto_parser
            ofproto = datapath.ofproto 
            
            # Priority 1
            # Delete MAC to port flows
            if dpid in self.mac_to_port:
                for dst in self.mac_to_port[dpid].keys():
                    match = parser.OFPMatch(eth_dst=dst)
                    mod = parser.OFPFlowMod(
                        datapath, command=ofproto.OFPFC_DELETE,
                        out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                        priority=1, match=match)
                    datapath.send_msg(mod)
                # Delete mac_to_port entry
                self.mac_to_port[dpid].clear()

            # priority 2
            match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=SERVICE_IP) #, tcp_dst=SERVICE_PORT) require ip_proto=TCP        
            mod = parser.OFPFlowMod(datapath, command=ofproto.OFPFC_DELETE,
                    out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                    priority=CLIENT_PRIORITY, match=match)
            datapath.send_msg(mod)

            # priority 3
            for svr in self.servers:
                ip_dst = "192.168.0." + svr[6:] # cut off "server" from name 
                match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=ip_dst) #, tcp_dst=SERVICE_PORT) require ip_proto=TCP        
                mod = parser.OFPFlowMod(datapath, command=ofproto.OFPFC_DELETE,
                        out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                        priority=SERVER_PRIORITY, match=match)
                datapath.send_msg(mod)
        


    # TODO: algorithm can be optimized, just cut off calculated paths
    # Alternative version, in res are saved pairs (child, dst)
    #  where dst specify the leaf value
    def server_slices(self, clients): # client+servers
        clients = clients + self.servers 
        # Transform self.links into graph
        graph = {}
        for dpid in self.links:
            for node2 in self.links[dpid]:
                node1 = "switch{}".format(dpid)
                graph.setdefault(node1, [])
                graph.setdefault(node2, [])
                if node2 not in graph[node1]:
                    graph[node1].append(node2)
                if node1 not in graph[node2]:
                    graph[node2].append(node1)

        self.logger.debug("GRAPH: ")
        self.logger.debug(graph)
        
        # Algorithm to create optimized spanning tree
        tree = {} # can be saved globally
        q = [ self.curr_server ]
        visited = []
        while len(q) > 0:
            curr = q.pop(0)
            visited.append(curr)
            for next in graph[curr]:
                if next not in visited:
                    q.append(next)
                    tree[next] = curr
        
        # Reverse tree
        res = {}
        visited = []
        for client in clients:
            # root is now pair (child: {dst})
            root = client # can be used with every new client 
            while root in tree: # the paths are repeated
                visited.append(root)
                res.setdefault(tree[root], {})
                res[tree[root]].setdefault(root, [])
                res[tree[root]][root].append(client) 
                root = tree[root]

        self.logger.debug("SERVER_RES")
        self.logger.debug(res)
        return res

    def apply_slicing(self, slicing, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id 
        out_port = None 
        
        self.delete_flows()

        # Close open ports
        for dp in self.open_ports:
            for num in self.open_ports[dp]:
                port = self.datapaths[dp].ports[num]
                PORT_NO_FORWARD = ofproto.OFPPC_NO_FWD  # imposta i flag
                mask = 0b1100101
                _msg = parser.OFPPortMod(self.datapaths[dp], port.port_no, port.hw_addr,
                                        PORT_NO_FORWARD, mask, port.advertised)
                self.datapaths[dp].send_msg(_msg)
                self.logger.debug("Port <{}> of <switch{}> is closed".format(port.name.decode(), dp))
            
            self.open_ports[dp].clear()
        
        for node1 in slicing:
            for node2 in slicing[node1]:
                # Open port from node to child
                if "switch" in node1:
                    dpid1 = int(node1[6:])
                    self.open_ports[dpid1].add(self.links[dpid1][node2])

                # Add uprising flow to current server (priority = 2)
                if "switch" in node2:
                    # Add new flow to node2, so it will send packets to current server
                    _dpid = int(node2[6:])
                    out = self.links[_dpid][node1]
                    actions = [parser.OFPActionOutput(out)]
                    self.logger.debug("{} sends on port {} to {}".format(node2, out, node1))
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=SERVICE_IP) #, tcp_dst=SERVICE_PORT) require ip_proto=TCP
                    # Update switch with new flow
                    self.add_flow(self.datapaths[_dpid], CLIENT_PRIORITY, match, actions)
                    # priority 2 => client slice
                    if "server" not in node1:
                        self.open_ports[_dpid].add(out)
                    
                    if dpid == _dpid:
                        out_port = out

                # Add flows to hosts (priority = 1)
                # TODO: save hosts MACs

                # Add descending flows to servers (priority = 3)
                for svr in self.servers:
                    # Private IP of servers are 192.168.0.[1-255]
                    # If start from switch and server is down in childs
                    if "switch" in node1 and svr in slicing[node1][node2]:
                        # Add new flow to node1, so it will send packets to figlio
                        ip_dst = "192.168.0." + svr[6:] # cut off "server" from name 
                        _dpid = int(node1[6:])
                        datapath = self.datapaths[_dpid]
                        parser = datapath.ofproto_parser
                        out = self.links[_dpid][node2]
                        actions = [parser.OFPActionOutput(out)]
                        self.logger.debug("{} sends on port {} to {}".format(node2, out, ip_dst))
                        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=ip_dst) #, tcp_dst=INTERNAL_PORT) require ip_proto=TCP
                        # Update switch with new flow
                        self.add_flow(self.datapaths[_dpid], SERVER_PRIORITY, match, actions)

                        self.open_ports[_dpid].add(out)

                    # Child must go up to reach the server
                    if "switch" in node2 and svr not in slicing[node1][node2]:
                        # Add new flow to figlio, so it will send packets to node1
                        _dpid = int(node2[6:])
                        datapath = self.datapaths[_dpid]
                        parser = datapath.ofproto_parser
                        ip_dst = "192.168.0." + svr[6:] # cut off "server" from name 
                        out = self.links[_dpid][node1]
                        actions = [parser.OFPActionOutput(out)]
                        self.logger.debug("{} sends on port {} to {}".format(node2, out, node1))
                        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=ip_dst) #, tcp_dst=INTERNAL_PORT) require ip_proto=TCP
                        # Update switch with new flow
                        self.add_flow(self.datapaths[_dpid], SERVER_PRIORITY, match, actions)

                        self.open_ports[_dpid].add(out)
                    

        # Open reserved_ports
        for dp in self.open_ports:
            for num in self.open_ports[dp]:
                port = self.datapaths[dp].ports[num]
                # Open port
                PORT_FORWARD = 0
                mask = 0b1100101
                _msg = parser.OFPPortMod(self.datapaths[dp], port.port_no, port.hw_addr,
                                        PORT_FORWARD, mask, port.advertised)
                self.datapaths[dp].send_msg(_msg)
                self.logger.debug("Port <{}> of <switch{}> is open".format(port.name.decode(), dp))

        return out_port

    def migrate(self, new_server):
        if new_server not in self.server_links:
            self.logger.error("\n\n[Cannot find server]\n\n")
            return 
        self.logger.info("Migrating to <{}>...".format(new_server))
        
        if new_server != self.curr_server:
            # Creating packet to start migration
            e = ethernet.ethernet(dst="00:00:00:cc:00:00",
                        src='08:60:6e:7f:74:e7', ethertype=ether.ETH_TYPE_IP)
            # Send packet to curr_server imitating new_server
            ip_src = "192.168.0." + new_server[6:]
            ip_dst = "192.168.0." + self.curr_server[6:]
            
            i = ipv4.ipv4(proto=17, src=ip_src, dst=ip_dst) # proto = 17 means UDP
            # src = IP of the new server
            # dst = IP of the current/old server
            u = udp.udp(src_port=MIGRATION_PORT, dst_port=MIGRATION_PORT)

            p = packet.Packet()
            p.add_protocol(e)
            p.add_protocol(i)
            p.add_protocol(u) 
            
            # Select switch to send packet
            dpid = list(self.server_links[self.curr_server].keys())[0] # take first dp close to server
            out_port = self.server_links[self.curr_server][dpid][0] # take first port of the dp
            datapath = self.datapaths[dpid]
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            actions = [parser.OFPActionOutput(out_port)]

            # construct packet_out message and send it.
            msg = parser.OFPPacketOut(datapath=datapath,
                                    buffer_id=ofproto.OFP_NO_BUFFER,
                                    in_port=10, actions=actions,
                                    data=p)
            datapath.send_msg(msg)
            # Leave some time to the active server to send the state
            time.sleep(2)
        
        # Change server, recalculate slicing
        self.curr_server = new_server
        slicing = self.server_slices(self.clients)
        datapath = list(self.datapaths.values())[0] # get first datapath
        self.apply_slicing(slicing, datapath)
        self.logger.info("Migrated")
        
        
    def register_switch(self, datapath):
        if datapath.id in self.datapaths:
            return 
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                        ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        dpid = datapath.id 
        self.logger.info("Registering switch{}...".format(dpid))
        self.datapaths[dpid] = datapath
        self.open_ports[dpid] = set() # empty set
        
        # add switch and its links to dictionaries
        self.links[dpid] = {}
        for port in datapath.ports.values():
            port_name = port.name.decode()
            # Simple filter
            if "-" in port_name:
                dst = port_name.split('-')[1] # take the destination
                self.links[dpid][dst] = port.port_no
                # Add servers to the list
                if "server" in port_name:
                    _, svr = port.name.split(b'-')
                    svr = svr.decode()

                    if svr not in self.servers:
                        self.servers.append(svr)
                    
                    svr_links = self.server_links.setdefault(svr, {})
                    svr_links.setdefault(dpid, []) 
                    svr_links[dpid].append(port.port_no)

                    if svr == self.curr_server:
                        continue 

                else:
                    # close all non server ports
                    self.logger.debug("Port down {}".format(port_name))
                    PORT_STATE_BLOCK = ofproto.OFPPC_NO_FWD
                    mask = 0b1100101
                    msg = parser.OFPPortMod(datapath, port.port_no, port.hw_addr,
                                    PORT_STATE_BLOCK, mask, port.advertised)
                    datapath.send_msg(msg)

        self.logger.debug(self.links)
        self.logger.debug("LINKS to servers: \n{}".format(self.server_links))
        self.logger.info(" <switch{}> registered".format(dpid))

    # When new switch appear OR any switch is deleted
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def switch_features_handler(self, ev):
        datapath = ev.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        if not datapath.id is None:
            if ev.state == MAIN_DISPATCHER:
                self.register_switch(datapath)
            elif ev.state == DEAD_DISPATCHER:
                # Extra: used only when mininet is relaunched,
                #  but controller remain active
                dpid = datapath.id
                self.logger.info("Unregistering switch{}...".format(dpid))
                if dpid in self.datapaths:
                    # Delete switch
                    del self.datapaths[dpid]
                    self.clients.clear()
                    del self.links[dpid]
                    del self.open_ports[dpid]
                    if dpid in self.mac_to_port:
                        del self.mac_to_port[dpid]
                    for server in self.server_links:
                        if dpid in self.server_links[server]:
                            del self.server_links[server][dpid]
        else:
            self.logger.debug("None event")
        
    def add_flow(self, datapath, priority, match, actions):
        self.logger.debug("    Flow with prior {} added to {}".format(priority, datapath.id))
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # construct flow_mod message and send it.
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    # When unmatched packet arrives
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # analyze the received packets using the packet library.
        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        dst = eth_pkt.dst
        src = eth_pkt.src

        #ip_pkt = pkt.get_protocol(ipv4.ipv4)
        #ip_dst = ip_pkt.ip_dst 
        #ip_src = ip_pkt.ip_src 

        if "33:" in dst: 
            return # just skip

        # get the received port number from packet_in message.
        in_port = msg.match['in_port']

        client = datapath.ports[in_port].name.split(b'-')[1].decode()
        # get Datapath ID to identify OpenFlow switches.
        dpid = datapath.id
        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        self.logger.debug("Unrecognized packet (type=0x{:x}) in <switch{}> on port:<{}> from MAC<{}> to MAC<{}>".format(eth_pkt.ethertype, dpid, in_port, src, dst))

        # if the destination mac address is already learned,
        #  decide which port to output the packet, otherwise FLOOD.
        if dst != src and dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD
            self.logger.debug("FLOOD\nMAC_TO_PORT {}".format(self.mac_to_port))

        self.logger.debug("Client= {}".format(client))
        if ("switch" not in client) and ("server" not in client) and client not in self.clients:
            self.logger.info("Adding <client{}>...".format(client))
            self.clients.append(client)
            # Calculate slicing
            slicing = self.server_slices(self.clients)
            out_port = self.apply_slicing(slicing, datapath)
            self.logger.info(" <client{}> added".format(client))
        else:
            # Send message forward
            actions = [parser.OFPActionOutput(out_port)]

            # install a flow to avoid packet_in next time.
            if out_port != ofproto.OFPP_FLOOD:
                self.logger.debug("Dst is known, out_port={}".format(out_port))
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                self.add_flow(datapath, 1, match, actions)

        # Send message forward
        #   construct action list.
        self.logger.debug(" forwarded to port: <{}>".format(out_port))
        actions = [parser.OFPActionOutput(out_port)]

        # construct packet_out message and send it.
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions,
                                  data=msg.data)
        datapath.send_msg(out)