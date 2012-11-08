#!/usr/bin/env python
# coding=utf-8

"""
Copyright 2012 Load Impact

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import division

import base64
import ConfigParser
import httplib
import json
import logging
import logging.config
import logging.handlers
import math
import optparse
import os
import Queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

if sys.platform.startswith('linux'):
    import resource

from collections import defaultdict
from urlparse import urlparse

try:
    import psutil
except ImportError:
    print "Can't find module psutil"
    sys.exit(1)

__author__ = "Load Impact"
__copyright__ = "Copyright 2012, Load Impact"
__license__ = "Apache License v2.0"
__version__ = "0.0.7"
__email__ = "support@loadimpact.com"

PROGRAM_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
CONFIG_FILE = os.path.join(PROGRAM_DIR, 'li_metrics_agent.conf')
if sys.platform.startswith('linux'):
    PANIC_LOG = '/var/log/li_metrics_panic.log'
else:
    PANIC_LOG = os.path.join(PROGRAM_DIR, 'li_metrics_panic.log')
PROTOCOL_VERSION = "1"
AGENT_USER_AGENT_STRING = ("LoadImpactServerMetricsAgent/%s "
                           "(Load Impact; http://loadimpact.com);"
                           % __version__)

DEFAULT_SERVER_METRICS_API_URL = 'http://api.loadimpact.com/v2/server-metrics'
DEFAULT_POLL_RATE = 30
DEFAULT_SAMPLING_INTERVAL = 3
DEFAULT_DATA_PUSH_INTERVAL = 10

UMASK = 0
WORK_DIR = "/"
MAX_FD = 1024
PID_FILE = "/var/run/li_metrics_agent.pid"


def daemonize():
    """Code copied from:
    http://code.activestate.com/recipes/278731-creating-a-daemon-the-python-way/

    Copyright (C) 2005 Chad J. Schroeder
    Licensed under the PSF License
    """
    if hasattr(os, "devnull"):
        REDIRECT_TO = os.devnull
    else:
        REDIRECT_TO = "/dev/null"

    try:
        pid = os.fork()
    except OSError, e:
        raise Exception("%s [%d]" % (e.strerror, e.errno))

    if pid == 0:
        os.setsid()
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

        try:
            pid = os.fork()
        except OSError, e:
            raise Exception("%s [%d]" % (e.strerror, e.errno))

        if pid == 0:
            os.chdir(WORK_DIR)
            os.umask(UMASK)
        else:
            os._exit(0)
    else:
        os._exit(0)

    maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if maxfd == resource.RLIM_INFINITY:
        maxfd = MAX_FD

    for fd in range(0, maxfd):
        try:
            os.close(fd)
        except OSError:
            pass

    os.open(REDIRECT_TO, os.O_RDWR)
    os.dup2(0, 1)
    os.dup2(0, 2)

    return 0


def log_dump():
    """Dump stack trace (one frame per line) to log."""
    tb = str(traceback.format_exc()).split("\n")
    logging.error("")
    for i, a in enumerate(tb):
        if a.strip():
            logging.error(a)


class AgentState(object):
    """The agent can only be in these states. Either sending data or not."""
    IDLE = 1
    ACTIVE = 2

    @staticmethod
    def get_name(state):
        return 'IDLE' if AgentState.IDLE == state else 'ACTIVE'

    @staticmethod
    def is_valid(state):
        return True if state in [AgentState.IDLE, AgentState.ACTIVE] else False


class ApiClient(object):
    """An API HTTP client class that has two states, poll and active. In active
    state a TCP connection will be kept alive across requests where as in poll
    state it will not.
    """

    def __init__(self, agent_name, api_token, api_url, proxy_url=None):
        self.agent_name = agent_name
        self.api_token = api_token
        self.parsed_api_url = urlparse(api_url)
        self.parsed_proxy_url = urlparse(proxy_url) if proxy_url else None
        self.state = AgentState.IDLE
        self.conn = None
        self.lock = threading.Lock()

    def _build_auth(self, username, password=''):
        return 'Basic %s' % base64.b64encode('%s:%s' % (username, password))

    def _connect(self):
        if not self.conn:
            if 'http' == self.parsed_api_url.scheme:
                port = self.parsed_api_url.port if self.parsed_api_url.port else 80
                self.conn = httplib.HTTPConnection(self.parsed_api_url.hostname,
                                                port=port)
            else:
                port = self.parsed_api_url.port if self.parsed_api_url.port else 443
                self.conn = httplib.HTTPSConnection(self.parsed_api_url.hostname,
                                                port=port)
            if self.parsed_proxy_url:
                headers = {}
                if self.parsed_proxy_url.username:
                    username = self.parsed_proxy_url.username
                    password = self.parsed_proxy_url.password
                    headers['Proxy-Authentication'] = self._build_auth(username,
                                                                       password)
                self.conn.set_tunnel(self.parsed_proxy_url.hostname,
                                     port=self.parsed_proxy_url.port,
                                     headers=headers)

    def _close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _request(self, method, data=None, headers=None):
        with self.lock:
            try:
                self._connect()
            except socket.gaierror:
                raise
            except httplib.HTTPException:
                raise

            headers = {} if not isinstance(headers, dict) else headers
            if 'Authorization' not in headers:
                headers['Authorization'] = self._build_auth(self.api_token)
            headers['User-Agent'] = AGENT_USER_AGENT_STRING

            self.conn.request(method, self.parsed_api_url.path, data, headers)
            resp = self.conn.getresponse()
            ret = (resp.status, resp.read())

            # Close connection if in IDLE mode otherwise leave open.
            if AgentState.IDLE == self.state:
                self._close()

            return ret

    def poll(self):
        data = {
            'name': self.agent_name,
            'version': PROTOCOL_VERSION,
            'version_agent': __version__
        }
        logging.debug(json.dumps(data))
        return self._request('POST',
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps(data))

    def push_batch(self, batch):
        data = []
        for x in batch:
            metric = {
                'name': self.agent_name,
                'version': PROTOCOL_VERSION,
                'version_agent': __version__,
                'label': x[0],
                'min': x[1],
                'max': x[2],
                'avg': x[3],
                'stddev': x[4],
                'median': x[5],
                'count': x[6],
                'unit': x[7]
            }
            data.append(metric)

        logging.debug(json.dumps(data))
        return self._request('PUT',
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps(data))


class Scheduler(object):
    """Scheduler is responsible for managing task threads. Each metric plugin
    has its own task.
    """

    def __init__(self):
        self.tasks = []

    def __repr__(self):
        rep = ''
        for task in self.tasks:
            rep += '%s\n' % repr(task)
        return rep

    def add_task(self, task):
        task.daemon = True
        self.tasks.append(task)

    def start(self):
        for task in self.tasks:
            logging.debug('starting %s', task)
            task.start()

    def stop(self, timeout=3):
        for task in self.tasks:
            logging.debug('stopping %s', task)
            task.stop()
            task.join(timeout=timeout)


class Reporting(threading.Thread):
    """
    Thread responsible for sending result data back to the API.
    """
    def __init__(self, queue, client):
        threading.Thread.__init__(self)

        self.queue = queue
        self.client = client

        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            batch = []
            # Empty queue
            while True:
                try:
                    data = self.queue.get_nowait()
                    batch.append(data)
                except Queue.Empty:
                    break

            if len(batch):
                status, body = self.client.push_batch(batch)
                if 201 != status:
                    logging.error("%d status code returned when pushing data "
                                  "to server: \"%s\"" % (status, repr(body)))

            time.sleep(2)


class Task(threading.Thread):
    """A task thread is responsible for collection and reporting of a single
    metric. The metric can be one of the built-in ones or a Nagios-compatible
    plugin that is executed as a sub-process.
    """

    def __init__(self, queue, client, cmd, sampling_interval,
                 data_push_interval):
        threading.Thread.__init__(self)
        self.queue = queue
        self.client = client
        self.cmd = cmd
        self.sampling_interval = sampling_interval
        self.data_push_interval = data_push_interval
        self.running = True
        self.state = AgentState.IDLE
        self.buffer = []
        self.prev_sent = 0
        self.prev_recv = 0
        self.last_push = time.time()

    def __repr__(self):
        return 'task %s' % (self.cmd)

    def _next_line(self):
        c = subprocess.Popen(self.cmd, shell=True, stdout=subprocess.PIPE)
        return c.stdout.next()

    def _prepare_data(self):
        count = len(self.buffer)

        # avg
        vmin = sys.float_info.max
        vmax = 0.0
        total = 0.0
        for v in self.buffer:
            vmin = min(vmin, v)
            vmax = max(vmax, v)
            total = total + v

        avg = total / count

        # std dev
        total = 0.0
        for v in self.buffer:
            total += ((v - avg) ** 2)

        stddev = 0.0
        if count > 1:
            stddev = math.sqrt((1.0 / (count - 1)) * total)

        # median
        values = sorted(self.buffer)
        if count % 2 == 1:
            median = values[int((count + 1) / 2 - 1)]
        else:
            lower = values[int(count / 2 - 1)]
            upper = values[int(count / 2)]
            median = (float(lower + upper)) / 2

        return (vmin, vmax, avg, stddev, median, count)

    def push_data(self, label, value, unit):
        self.buffer.append(float(value))
        if (self.last_push + self.data_push_interval) < time.time():
            try:
                data = self._prepare_data()
                data = (label,) + data + (unit,)

                try:
                    self.queue.put_nowait(data)
                except Queue.Full:
                    pass  # Ignore data

                self.last_push = time.time()
                self.buffer = []
            except Exception:
                log_dump()

    def run(self):
        execution_time = time.time()
        while self.running:
            start = time.time()
            try:
                if AgentState.ACTIVE == self.state:
                    logging.debug('running %s ', self.cmd)
                    line = self._next_line()
                    # todo: improve this regexp
                    rex = re.match(r'^.*\|(.*)=([0-9.]+)([a-zA-Z%/]+)', line)
                    self.push_data(rex.group(1), rex.group(2), rex.group(3))
            except Exception:
                log_dump()
            execution_time += self.sampling_interval
            time.sleep(max(0, execution_time - start))

    def set_state(self, state):
        self.state = state

    def stop(self):
        self.running = False


class BuiltinMetricTask(Task):
    def _next_line(self):
        unknown_line = "unknown 0|unknown=0%;"
        args = [s for s in re.split(r'( |".*?"|\'.*?\')', self.cmd)
                if s.strip()]
        if len(args) < 1:
            logging.error('missing argument(s) for BUILTIN: ' + self.cmd)
            return unknown_line
        line = self._next_line_builtin(args)
        return line if line else unknown_line

    def _next_line_builtin(self, args):
        raise NotImplementedError


class CPUMetricTask(BuiltinMetricTask):
    """Built-in metric task to measure CPU utilization %."""

    def _next_line_builtin(self, args):
        if len(args) > 2:
            cpu_index = int(args[2], 10)
            cpu = psutil.cpu_percent(interval=1, percpu=True)
            try:
                cpu = cpu[cpu_index]
                return "CPU %d load %s%%|CPU=%s%%;" % (cpu_index, cpu, cpu)
            except IndexError:
                logging.error("incorrect CPU index: %d" % cpu_index)
                return None
        else:
            cpu = psutil.cpu_percent(interval=1)
            return "CPU load %s%%|CPU=%s%%;" % (cpu, cpu)


class MemoryMetricTask(BuiltinMetricTask):
    """Built-in metric task to measure physical memory utilization %."""

    def _next_line_builtin(self, args):
        phymem = psutil.phymem_usage()
        return "Memory usage %s%% |Memusage=%s%%;" % (phymem.percent,
                                                      phymem.percent)


class RateBasedMetrics(BuiltinMetricTask):
    """Base class for built-in metric tasks that are rate-based."""

    def __init__(self, *args, **kwargs):
        super(RateBasedMetrics, self).__init__(*args, **kwargs)
        self.prev = defaultdict(int)

    def _calculate_total(self, current, prev):
        total = 0
        p = self.prev[prev]
        if p > 0:
            total = current - p
        self.prev[prev] = current
        return total

    def _calculate_total2(self, sent, prev_sent, recv, prev_recv):
        total = 0
        prevs = self.prev[prev_sent]
        prevr = self.prev[prev_recv]
        if prevs > 0:
            total = (sent - prevs) + (recv - prevr)
        self.prev[prev_sent] = sent
        self.prev[prev_recv] = recv
        return total


class NetworkMetricTask(RateBasedMetrics):
    """Built-in metric task to measure network utilization metrics:
        - Bps (total, in and out)
        - Packets/s (total, in and out)
    """
    def _next_line_builtin(self, args):
        valid_metrics = ['bps', 'bps-in', 'bps-out', 'pps', 'pps-in', 'pps-out']
        interface = ""
        if len(args) > 1 and args[1].lower() not in valid_metrics:
            interface = args[1].replace("'", "")
            counters = psutil.network_io_counters(pernic=True)
            try:
                counters = counters[interface]
            except KeyError:
                logging.error("incorrect network interface name: "
                              "\"%s\"" % interface)
                return None
            # Format for label name in the report line below
            interface = " " + interface
        else:
            counters = psutil.network_io_counters(pernic=False)

        metric = 'bps'
        metric_index = 2 if interface else 1
        if len(args) > metric_index:
            metric = args[metric_index].lower()
            if metric not in valid_metrics:
                metric = 'bps'

        if metric == 'bps':
            total = self._calculate_total2(counters.bytes_sent, 'bytes_sent',
                                           counters.bytes_recv, 'bytes_recv')
        elif metric == 'bps-in':
            total = self._calculate_total(counters.bytes_recv, 'bytes_recv')
        elif metric == 'bps-out':
            total = self._calculate_total(counters.bytes_sent, 'bytes_sent')
        elif metric == 'pps':
            total = self._calculate_total2(counters.packets_sent,
                                           'packets_sent',
                                           counters.packets_recv,
                                           'packets_recv')
        elif metric == 'pps-in':
            total = self._calculate_total(counters.packets_recv, 'packets_recv')
        elif metric == 'pps-out':
            total = self._calculate_total(counters.packets_sent, 'packets_sent')

        metric_ps = total / self.sampling_interval / 1024
        line = ("%s over %s sec|Network%s=%.2f%s"
                % (total, self.sampling_interval, interface, metric_ps, metric))

        return line


class DiskMetricTask(RateBasedMetrics):
    """Built-in metric task to measure disk utilization metrics:
        - IOps (total, in and out)
        - Bps (total, in and out)
        - Usage (used space in percent)
    """
    def _next_line_builtin(self, args):
        valid_metrics = ['iops', 'ips', 'ops', 'bps', 'bps-in', 'bps-out',
                         'used']

        metric = 'iops'
        if len(args) > 1:
            metric = args[1].lower()
            if metric not in valid_metrics:
                metric = 'iops'

        if metric == 'used':
            path = '/' if len(args) < 3 else args[2].replace("'", "")
            try:
                usage = psutil.disk_usage(path)
                total = usage.percent
            except OSError:
                logging.error("disk usage: path \"%s\" not found" % path)
                return None

            return ("Disk usage for %s|Disk=%.2f%%" % (path, total))
        else:
            counters = psutil.disk_io_counters()
            if metric == 'iops':
                total = self._calculate_total2(counters.write_count,
                                               'write_count',
                                               counters.read_count,
                                               'read_count')
            elif metric == 'ips':
                total = self._calculate_total(counters.read_count,
                                              'read_count')
            elif metric == 'ops':
                total = self._calculate_total(counters.write_count,
                                              'write_count')
            elif metric == 'bps':
                total = self._calculate_total2(counters.write_bytes,
                                               'write_bytes',
                                               counters.read_bytes,
                                               'read_bytes')
            elif metric == 'bps-in':
                total = self._calculate_total(counters.read_bytes,
                                              'read_bytes')
            elif metric == 'bps-out':
                total = self._calculate_total(counters.write_bytes,
                                              'write_bytes')

            metric_ps = total / self.sampling_interval
            line = ("Disk %d over %s sec|Disk=%.2f%s"
                    % (total, self.sampling_interval, metric_ps, metric))
            return line


class AgentLoop(object):
    """Agent main loop. Setup logging, parse config file, setup metric
    collection tasks and start scheduler.
    """

    def __init__(self):
        self.running = False
        self.state = AgentState.IDLE
        self.config = ConfigParser.ConfigParser()
        self.config.read(CONFIG_FILE)
        try:
            agent_name = self.config.get('General', 'agent_name')
            api_token = self.config.get('General', 'server_metrics_api_token')
        except ConfigParser.NoSectionError:
            logging.error("agent name (agent_name) and API token "
                          "(server_metrics_api_token) are mandatory "
                          "configuration variables under the \"General\" "
                          "section")
            sys.exit(1)
        api_url = (
            self.config.get('General', 'server_metrics_api_url')
            if self.config.has_option('General', 'server_metrics_api_url')
            else DEFAULT_SERVER_METRICS_API_URL)
        proxy_url = (
            self.config.get('General', 'proxy_url')
            if self.config.has_option('General', 'proxy_url')
            else None)
        self.poll_rate = (self.config.get('General', 'poll_rate')
                          if self.config.has_option('General', 'poll_rate')
                          else DEFAULT_POLL_RATE)
        self.sampling_interval = (
            self.config.get('General', 'sampling_interval')
            if self.config.has_option('General', 'sampling_interval')
            else DEFAULT_SAMPLING_INTERVAL)
        self.data_push_interval = (
            self.config.get('General', 'data_push_interval')
            if self.config.has_option('General', 'data_push_interval')
            else DEFAULT_DATA_PUSH_INTERVAL)

        self.client = ApiClient(agent_name, api_token, api_url, proxy_url)
        self.scheduler = Scheduler()
        self.queue = Queue.Queue(maxsize=100)

        self.reporter = Reporting(self.queue, self.client)
        self.reporter.daemon = True

    def _parse_commands(self):
        # Configuration options named 'command' are our tasks.
        try:
            for section in self.config.sections():
                if self.config.has_option(section, 'command'):
                    cmd = self.config.get(section, 'command')
                    if cmd.lower().startswith('builtin'):
                        cmd_args = [s for s in re.split(r'( |".*?"|\'.*?\')',
                                                        cmd) if s.strip()][1:]
                        cmd = cmd_args[0].lower()
                        args = (self.queue, self.client, ' '.join(cmd_args),
                                self.sampling_interval,
                                self.data_push_interval)
                        if 'cpu' == cmd:
                            self.scheduler.add_task(CPUMetricTask(*args))
                        elif 'memory' == cmd:
                            self.scheduler.add_task(MemoryMetricTask(*args))
                        elif 'network' == cmd:
                            self.scheduler.add_task(NetworkMetricTask(*args))
                        elif 'disk' == cmd:
                            self.scheduler.add_task(DiskMetricTask(*args))
                        else:
                            logging.warning("unknown built-in command: \"%s\""
                                            % args[0])
                    else:
                        self.scheduler.add_task(Task(self.queue, self.client,
                                                     cmd,
                                                     self.sampling_interval,
                                                     self.data_push_interval))
        except Exception:
            logging.error("failed parsing commands configuration file")
            log_dump()
            sys.exit(1)

    def run(self):
        self._parse_commands()

        self.reporter.start()
        self.scheduler.start()
        self.running = True
        execution_time = time.time()

        try:
            while self.running:
                start = time.time()
                try:
                    # Poll server to see if we should switch state (start or
                    # stop sending collected data to server) or alter poll rate.
                    status, body = self.client.poll()
                    if 200 == status:
                        try:
                            j = json.loads(body)
                        except ValueError:
                            logging.error("unable to parse body as JSON: \"%s\""
                                          % repr(body))
                            continue

                        try:
                            state = int(j['state'])
                            if state != self.state:
                                self.state = state
                                if AgentState.is_valid(state):
                                    for task in self.scheduler.tasks:
                                        task.set_state(state)
                                    state_name = AgentState.get_name(state)
                                    logging.debug("switching state to %s "
                                                  "(%d)"
                                                  % (state_name, state))
                                else:
                                    logging.error("received invalid state "
                                                  "from server: %d" % state)
                        except KeyError:
                            logging.error("'state' not found in JSON response")
                        except ValueError:
                            logging.error("type coercion failed: 'state' "
                                          "(\"%s\") to int"
                                          % str(j['state']))

                        try:
                            self.poll_rate = int(j['poll_rate'])
                        except KeyError:
                            logging.error("'poll_rate' not found in JSON "
                                          "response")
                        except ValueError:
                            logging.error("type coercion failed: 'poll_rate' "
                                          "(\"%s\") to int" % str(j['state']))
                    else:
                        logging.error("%d status code returned when "
                                      "polling server API for state: \"%s\""
                                      % (status, repr(body)))
                except Exception:
                    log_dump()
                finally:
                    execution_time += max(10, min(3600, self.poll_rate))
                    time.sleep(max(0, execution_time - start))
            self.scheduler.stop()
        except KeyboardInterrupt:
            self.scheduler.stop()

    def stop(self):
        self.running = False


if __name__ == "__main__":
    p = optparse.OptionParser(version=('%%prog %s' % __version__))
    p.add_option('-D', '--no-daemon', action='store_false',
                 dest='daemon', default=True,
                 help=("When this option is specified, the agent will not "
                       "detach and does not become a daemon."))
    opts, args = p.parse_args()

    if opts.daemon:
        retcode = daemonize()

    try:
        logging.config.fileConfig(CONFIG_FILE)
    except ConfigParser.NoSectionError, e:
        # We ignore any parsing error of logging configuration variables.
        pass
    except Exception, e:
        # Parsing of logging configuration failed, print something to a panic
        # file in /var/log (Linux) or [Program] directory (Windows).
        try:
            with open(PANIC_LOG, 'r') as f:
                f.write("failed parsing logging configuration: %s" % repr(e))
        except IOError:
            pass
        sys.exit(1)

    if opts.daemon:
        logging.debug("load impact server metrics agent daemonization "
                      "returned: %d" % retcode)

    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except IOError, e:
        logging.debug("unable to write pid file \"%s\": %s" % (PID_FILE,
                                                               repr(e)))

    if not opts.daemon:
        print 'press Ctrl-C to stop me'

    loop = AgentLoop()
    loop.run()

    if not opts.daemon:
        print 'ok ok, bye bye!'
    else:
        sys.exit(retcode)
