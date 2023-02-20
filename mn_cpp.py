#!/usr/bin/env python

import sys
import aoi
import os

from mininet.log import setLogLevel, info
from mn_wifi.cli import CLI
from mn_wifi.net import Mininet_wifi
from time import sleep
from multiprocessing import Process, Queue


def run_cmd(idx, hosts, res_queue):
    res_arr = res_queue.get()
    res_arr[idx] = hosts[idx].cmd('./sperf/sender ' + `idx + 1`)
    res_queue.put(res_arr)


def net_run(graph):
    "Create a network."
    net = Mininet_wifi()

    info("*** Creating nodes\n")
    sta_arg, ap_arg = {}, {}
    if '-v' in sys.argv:
        sta_arg = {'nvif': 2}
    else:
        ap_arg = {'client_isolation': True}

    n_hosts = len(graph)
    ap_arr = []
    hosts_arr = []
    for i in range(n_hosts):
        ap_arr.append(net.addAccessPoint('ap' + `i + 1`, 
                      ssid="simpletopo", mode="g",
                      channel="5", **ap_arg))
        hosts_arr.append(net.addHost('h' + `i + 1`))
    c0 = net.addController('c0')

    info("*** Configuring nodes\n")
    net.configureNodes()

    info("*** Associating Hosts\n")
    for i in range(n_hosts):
        net.addLink(hosts_arr[i], ap_arr[i])

    for row in range(n_hosts):
        for col in range(row, n_hosts):
            if graph[row][col] == True:
                net.addLink(ap_arr[row], ap_arr[col])

    info("*** Starting network\n")
    net.build()
    c0.start()
    for i in range(n_hosts):
        ap_arr[i].start([c0])

    protocols = ['arp', 'icmp', 'udp', 'tcp']
    if '-v' not in sys.argv:
        for i in range(n_hosts):
            for protocol in protocols:
                ap_arr[i].cmd('ovs-ofctl add-flow ap' + `i + 1` + 
                              ' "priority=0,' + protocol + ',in_port=1,'
                              'actions=output:in_port,normal"')
       
    #info("*** Running CLI\n")
    #CLI(net)

    res_str_arr = ["" for _ in range(n_hosts)]
    res_queue = Queue();
    res_queue.put(res_str_arr)
    threads = [Process(target=run_cmd, args=(i, hosts_arr, res_queue)) for i in range(1, n_hosts)]

    info("*** Running SPERF\n")
    info("***** SPERF receiver on\n")
    hosts_arr[0].cmd('./sperf/receiver ' + `n_hosts` + ' &')
    sleep(1)

    for i in range(n_hosts - 1):
        info("***** SPERF sender no." + `i + 2` + " on\n")
        threads[i].start()

    for i in range(n_hosts - 1):
        threads[i].join()
        info("***** SPERF sender no." + `i + 2` + " off\n")

    res_str_arr = res_queue.get()

    info("*** Stopping network\n")
    net.stop()

    return res_str_arr


def write_results(test_num, delays_arr, voi_arr, pvoi_arr):
    fp = open("./result/result_" + `test_num` + ".txt", 'w')

    for delays in delays_arr:
        fp.write(' '.join(`num` for num in delays) + "\n")

    fp.write(' '.join(`num` for num in voi_arr) + "\n")
    fp.write(' '.join(`num` for num in pvoi_arr) + "\n")

    fp.write(`sum(voi_arr)` + "\n")
    fp.write(`sum(pvoi_arr)` + "\n")
    fp.close()


def read_metadata():
    fp = open("metadata.txt", 'r')
    metadata = fp.readlines()
    fp.close()
    return metadata


def read_topology(test_num):
    fp = open("./topology/topo_" + `test_num` + ".txt", 'r')
    topo_str_arr = fp.readlines()
    fp.close()

    topo = []
    n_row = len(topo_str_arr[0]) - 1
    for row in range(n_row):
        topo_row = []
        for col in range(n_row):
            topo_row.append(True if topo_str_arr[row][col] == 'T' else False)
        topo.append(topo_row)
    return topo


def get_freq(metadata):
    freq_str = metadata.split()[1]
    res = 0
    for c in freq_str:
        if '0' <= c <= '9':
            res *= 10
            res += int(c)
    return res


def get_freq_arr(metadata_arr):
    freq_arr = []
    for metadata in metadata_arr:
        freq_arr.append(get_freq(metadata))
    return freq_arr


def get_delays_arr(res_str_arr):
    delays_arr = []
    for i in range(1, len(res_str_arr)):
        delays_arr.append(list(map(int, res_str_arr[i].split())))
    return delays_arr


def get_ltt(delays_arr, freq_arr):
    ltt = 0
    for i in range(len(delays_arr)):
        n_delays = len(delays_arr[i])
        last_delay = delays_arr[i][-1]
        ltt = max(ltt, float((1000 // freq_arr[i]) * (n_delays - 1) + last_delay) / 1000.0)
    return ltt


def is_realtime_data(metadata):
    realtime_str = metadata.split()[3]
    return realtime_str[0] == 'r'


def get_voi(aoi_fn_arr, metadata, delays, freq):
    aoi_fn_idx = 0 if is_realtime_data(metadata) == True else 1
    aoi_fn = aoi_fn_arr[aoi_fn_idx]

    voi = aoi_fn.get_voi(delays, freq)
    pvoi = aoi_fn.get_pvoi(delays, freq)

    return (voi, pvoi)


def is_error_occurred(res_str_arr):
    for i in range(1, len(res_str_arr)):
        if not ('0' <= res_str_arr[i][0] <= '9'):
            return True
    return False


if __name__ == '__main__':
    setLogLevel('info')
    test_num = int(sys.argv[1])

    print("\n\n* Test No." + `test_num + 1`)
    metadata_arr = read_metadata()
    graph = read_topology(test_num)
    res_str_arr = net_run(graph)

    if is_error_occurred(res_str_arr):
        print(res_str_arr)
        exit()

    delays_arr = get_delays_arr(res_str_arr) 
    freq_arr = get_freq_arr(metadata_arr)
    ltt = get_ltt(delays_arr, freq_arr)
    voi_arr = []
    pvoi_arr = []

    for i in range(len(delays_arr)):
        metadata = metadata_arr[i]
        delays = delays_arr[i]
        freq = freq_arr[i]
        time_step = 1.0 / float(freq)
        aoi_r = aoi.AoI((lambda x: x if x <= time_step else x * 2), ltt)
        aoi_n = aoi.AoI((lambda x: x / 2.0), ltt)
        aoi_fn_arr = [aoi_r, aoi_n]

        voi, pvoi = get_voi(aoi_fn_arr, metadata, delays, freq)
        voi_arr.append(voi)
        pvoi_arr.append(pvoi)

    write_results(test_num, delays_arr, voi_arr, pvoi_arr)

