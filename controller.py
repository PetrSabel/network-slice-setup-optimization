from operator import attrgetter
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
from slicing import Slicing

class Monitor(Slicing):
    def __init__(self, *args, **kwargs):
        super(Monitor, self).__init__(*args, **kwargs)
        # Note: threads share the events so the monitor must be fast
        self.monitor_thread = hub.spawn(self._monitor)
        self.bw = {} # server -> [bytes,secs,bw]

    def _monitor(self):
        while True:
            hub.sleep(10)
            try:
                self.logger.info("{}".format(self.servers))
                for new_server in self.servers:
                    # Migrate to each server
                    self.logger.debug("Trying to migrate to <{}>".format(new_server))
                    self.migrate(new_server) 

                    # Take all switches connected to the current server
                    switches = []
                    for sw in self.server_links[self.curr_server]:
                        switches.append(sw)

                    # Setting def values for server bandwidth
                    self.bw[self.curr_server] = [0, 0, 0].copy()
                    hub.sleep(10)
                    
                    for i in switches:
                        self._request_stats(self.datapaths[i])
                    hub.sleep(10) # let switches time to respond
                    
                    # Read bandwidth
                    B, sec ,_ = self.bw[self.curr_server]
                    self.logger.debug("After {}B {}s".format(B, sec))

                    if sec != 0:
                        # Calculate actual bandwidth
                        self.bw[self.curr_server] = [B, sec, B/sec].copy()
                        self.logger.info("<{}> bandwidth: {}B/s".format(self.curr_server, self.bw[self.curr_server][2]))

                # Choose the optimal server
                new_server = self.servers[0]
                higher_bw = 0
                for server in self.bw:
                    _,_,bw = self.bw[server]
                    if higher_bw < bw:
                        higher_bw = bw
                        new_server = server

                # Migrate to optimal server
                self.migrate(new_server)
                hub.sleep(10)
                self.logger.info("\nServer has been migrated on <{}>".format(new_server))

                # Service time
                hub.sleep(50)
            except Exception as e:
                print("Cannot migrate for some reason")
                print(e)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body
    
        self.logger.debug('datapath         '
                        'out-port packets  bytes')
        self.logger.debug('---------------- '
                        '-------- -------- --------')
        # Filter flows by priority and take the only ones destinated to the server
        # Cutting off all unintended traffic: 
        #  internal traffic between servers, packets between hosts, lost packets
        for stat in [flow for flow in body if flow.priority == 2]:
            self.logger.debug('%016x %8x %8d %8d',
                            ev.msg.datapath.id,
                            stat.instructions[0].actions[0].port,
                            stat.packet_count, stat.byte_count)
            # Sum bytes transmitted 
            self.bw[self.curr_server][0] += stat.byte_count
            self.bw[self.curr_server][1] = stat.duration_sec

    # Ports stats are not very accurate                    
            