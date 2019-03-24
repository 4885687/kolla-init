#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Time    : 2019/1/28 19:30
# Author  : Eric.Zhang
import argparse
import logging
import sys
import json
import os
import socket
import subprocess

import docker


FILE_PATH = os.path.abspath(__file__)
LOG = logging.getLogger(__name__)

# NOTE: zabbix_server is expected run only on one node.
# So skip it in case of report as problem.
# cobbler and registry may be stoppped.
SKIP_CONTAINERS = (
    'zabbix_server',
    'cobbler',
    'registry'
)


def get_client(*args, **kwargs):
    try:
        client = docker.Client(*args, **kwargs)
    except AttributeError:
        client = docker.APIClient(*args, **kwargs)
    return client


def lld_container(conf):
    client = get_client()
    containers = client.containers(all=True)
    data = []
    for container in containers:
        name = container['Names'][0][1:]
        if name in SKIP_CONTAINERS:
            continue
        data.append({"{#NAME}": name})
    return json.dumps({'data': data},indent=4,separators=(',',':'))


func_mapping = {
    'pids': lambda x: x.get('pids_stats', {}).get('current', 0),
    'ram': lambda x: x['memory_stats']['stats']['total_rss'],
}


def get_container_stat(name):
    client = get_client()
    container = client.containers(filters={'name': name}, all=True)
    if len(container) < 1:
        return 2
    elif container[0]['Status'].startswith('Up'):
        return 1
    elif len(container) > 1:
        return 3
    else:
	 return 0


def usage():
    usages = []
    usages.append('UserParameter=container.list[*],%s list' % FILE_PATH)
    usages.append('UserParameter=container.get[*],%s get -n $1' % FILE_PATH)
    return '\n'.join(usages)


def send(conf):
    from multiprocessing.pool import ThreadPool
    import threading

    tp = ThreadPool(40)

    def get_stats(name):
        LOG.debug('In threading: %s', threading.currentThread().name)
        stats = client.stats(name, stream=False)
        return name, stats

    client = get_client()
    results = []
    LOG.debug('Getting all containers')
    containers = client.containers(all=True)
    for container in containers:
        name = container['Names'][0][1:]
        if name in SKIP_CONTAINERS:
            continue
        # skip non-running containers
        if container['State'] != 'running':
            continue
        LOG.debug('Geting stats for %s', name)
        results.append(tp.apply_async(get_stats, (name, )))

    packets = []
    for result in results:
        name, stats = result.get(timeout=20)
        for key, func in func_mapping.items():
            stat = func(stats)
            LOG.debug('Get stats for [%s, %s]: %s', name, key, stat)
            packets.append(('container.send[%s,%s]' % (name, key), stat))

    for container in containers:
        name = container['Names'][0][1:]
        if name in SKIP_CONTAINERS:
            continue
        is_running = 0
        if container['State'] == 'running':
            is_running = 1
        key = 'container.send[%s,running]' % name
        packets.append((key, is_running))

    with open('/tmp/zabbix_sender.txt', 'w') as f:
        for key, value in packets:
            f.write('%s %s %s\n' % (conf.hostname, key, value))
    try:
        cmd = ['zabbix_sender', '-c', '/etc/zabbix/zabbix_agentd.conf', '-i',
               '/tmp/zabbix_sender.txt']
        if conf.debug:
            cmd.append('--verbose')
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        LOG.error('%s', e.output)
        raise
    LOG.info(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hostname', '-H', default=socket.gethostname())
    parser.add_argument('--container-name', '-n')
    parser.add_argument('--resource', '-r')
    parser.add_argument('--target', '-t')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('action',
                        choices=['list', 'get', 'test', 'usage', 'send'],
                        help='action')
    conf = parser.parse_args(sys.argv[1:])

    level = logging.INFO
    if conf.debug:
        level = logging.DEBUG
    logging.basicConfig(level=level)

    if conf.action == 'list':
        ret = lld_container(conf)
    elif conf.action == 'usage':
        ret = usage()
    elif conf.action == 'get' and conf.container_name:
        ret = get_container_stat(conf.container_name)
    elif conf.action == 'send':
        ret = send(conf)
    else:
        raise ValueError('Unknow parameters:%s', sys.argv[1:])
    print(ret)


if __name__ == "__main__":
    main()

