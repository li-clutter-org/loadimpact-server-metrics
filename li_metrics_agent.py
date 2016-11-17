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
import codecs
import ConfigParser
# set_tunnel() is not supported in Python26
import json
import logging
import logging.config
import logging.handlers
import math
import optparse
import os
import platform
import Queue
import re
import signal
import subprocess
import sys
import threading
import time
import traceback

if sys.version_info < (2,7):
   import httplib27 as httplib
   import socket27 as socket
else:
   import httplib
   import socket

running_on_linux = sys.platform.startswith('linux')
if running_on_linux:
    import resource

from collections import defaultdict
from datetime import datetime
from urlparse import urlparse

try:
    import psutil
except ImportError:
    print "can't find module psutil"
    sys.exit(1)

__author__ = "Load Impact"
__copyright__ = "Copyright (c) 2012, Load Impact"
__license__ = "Apache License v2.0"
__version__ = "1.1"
__email__ = "support@loadimpact.com"

frozen = getattr(sys, 'frozen', '')
if not frozen:
    # regular python
    PROGRAM_DIR = os.path.dirname(os.path.realpath(__file__))
else:
    # running in py2exe
    PROGRAM_DIR = os.path.dirname(os.path.realpath(sys.executable))

CONFIG_FILE = os.path.join(PROGRAM_DIR, 'li_metrics_agent.conf')
PANIC_LOG_FILENAME = 'li_metrics_panic.log'
if sys.platform.startswith('linux'):
    PANIC_LOG_PATH = '/var/log/%s' % (PANIC_LOG_FILENAME)
else:
    PANIC_LOG_PATH = os.path.join(PROGRAM_DIR, PANIC_LOG_FILENAME)
PROTOCOL_VERSION = "1"
PLATFORM_STRING = platform.platform()
AGENT_USER_AGENT_STRING = ("LoadImpactServerMetricsAgent/%s "
                           "(Load Impact; http://loadimpact.com);"
                           % __version__)
CONFIG_CMD_ARGS_REGEX = re.compile(r'( |"[^"]*?"|\'[^\']*?\')')
PERF_DATA_OPTS_REGEX = re.compile(r'''
    (?:([^:\'" ]+)|(?:(?:[\'"]?)([^:\'"]+)(?:[\'"]?)))  # Label
    (?::([a-zA-Z%/]+))?                                 # Unit
    (?:[ ]*)                                            # Multi-value separator
    ''', re.X)
NAGIOS_PERF_DATA_REGEX = re.compile(r'''
    (?:[\'"]?)([^=\'"]+)(?:[\'"]?)  # Label
    =
    ([\d\.]+)                       # Value
    ([a-zA-Z%/]+)?                  # Unit
    (?:;([\d\.]+)?)?                # Warning level
    (?:;([\d\.]+)?)?                # Critical level
    (?:;([\d\.]+)?)?                # Min
    (?:;([\d\.]+)?)?                # Max
    (?:[, ]*)                       # Multi-value separator
    ''', re.X)

DEFAULT_SERVER_METRICS_API_URL = 'http://api.loadimpact.com/v2/server-metrics'
DEFAULT_POLL_RATE = 30
DEFAULT_SAMPLING_INTERVAL = 3
DEFAULT_DATA_PUSH_INTERVAL = 10

UMASK = 0
WORK_DIR = "/"
MAX_FD = 1024
PID_FILE = "/var/run/li_metrics_agent.pid"


def panic_log(path, msg):
    with open(path, 'a') as f:
        f.write("%s - %s\n" % (datetime.now().isoformat(' '), msg))


def init_logging():
    try:
        logging.config.fileConfig(CONFIG_FILE)
    except ConfigParser.NoSectionError, e:
        # We ignore any parsing error of logging configuration variables.
        pass
    except Exception, e:
        # Parsing of logging configuration failed, print something to a panic
        # file in /var/log (Linux) or [Program] directory (Windows).
        try:
            panic_log(PANIC_LOG_PATH,
                      "failed parsing logging configuration: %s" % repr(e))
        except IOError:
            try:
                panic_log(PANIC_LOG_FILENAME,
                          "failed parsing logging configuration: %s" % repr(e))
            except IOError:
                print "failed parsing logging configuration: %s" % repr(e)
        sys.exit(1)


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


def check_output(*popenargs, **kwargs):
    """Based on check_output in Python 2.7 subprocess module."""
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    """https://github.com/pyinstaller/pyinstaller/wiki/Recipe-subprocess"""
    kwargs.pop('stdin', None)
    kwargs.pop('stderr', None)
    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    return output, retcode


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

class PsutilAdapter(object):
    """Adapter for psutil methods calls depends on psutil current version"""

    @staticmethod
    def normalized_version():
        # psutil versions are simple integers as x.x.x
        v = psutil.__version__
        return tuple(map(int, (v.split("."))))

    @classmethod
    def version_gte_than(self, version_tuple):
        return self.normalized_version() >= version_tuple

    @classmethod
    def net_io_counters(self, pernic=False):
        if self.version_gte_than((1,0,0)):
            return psutil.net_io_counters(pernic=pernic)
        else:
            return psutil.network_io_counters(pernic=pernic)

class NagiosPluginExitCode(object):
    """Enum mapping process exit codes to Nagios service states."""
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3

    @staticmethod
    def get_name(exit_code):
        if exit_code == NagiosPluginExitCode.OK:
            return 'OK'
        if exit_code == NagiosPluginExitCode.WARNING:
            return 'WARNING'
        elif exit_code == NagiosPluginExitCode.CRITICAL:
            return 'CRITICAL'
        elif exit_code == NagiosPluginExitCode.UNKNOWN:
            return 'UNKNOWN'
        return 'INVALID'


class ApiClient(object):
    """An API HTTP client class that has two states, poll and active. In active
    state a TCP connection will be kept alive across requests where as in poll
    state it will not.
    """

    def __init__(self, agent_name, token, api_url, proxy_url=None):
        self.agent_name = agent_name
        self.token = token
        self.parsed_api_url = urlparse(api_url)
        self.parsed_proxy_url = urlparse(proxy_url) if proxy_url else None
        self.state = AgentState.IDLE
        self.conn = None
        self.lock = threading.Lock()

    def _build_auth(self, username, password=''):
        return 'Basic %s' % base64.b64encode('%s:%s' % (username, password))

    def _connect(self):
        if not self.conn:
            scheme = (self.parsed_proxy_url.scheme if self.parsed_proxy_url
                      else self.parsed_api_url.scheme)
            host = (self.parsed_proxy_url.hostname if self.parsed_proxy_url
                    else self.parsed_api_url.hostname)
            port = (self.parsed_proxy_url.port if self.parsed_proxy_url
                    else self.parsed_api_url.port)
            if 'http' == scheme:
                port = port if port else 80
                self.conn = httplib.HTTPConnection(host, port=port)
            else:
                port = port if port else 443
                self.conn = httplib.HTTPSConnection(host, port=port)
            if self.parsed_proxy_url:
                host = self.parsed_api_url.hostname
                if 'http' == self.parsed_api_url.scheme:
                    port = (self.parsed_api_url.port if self.parsed_api_url.port
                            else 80)
                else:
                    port = (self.parsed_api_url.port if self.parsed_api_url.port
                            else 443)
                headers = {}
                if self.parsed_proxy_url.username:
                    username = self.parsed_proxy_url.username
                    password = self.parsed_proxy_url.password
                    headers['Proxy-Authentication'] = self._build_auth(username,
                                                                       password)
                self.conn.set_tunnel(host, port=port, headers=headers)

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
                headers['Authorization'] = self._build_auth(self.token)
            headers['User-Agent'] = AGENT_USER_AGENT_STRING

            try:
                self.conn.request(method, self.parsed_api_url.path, data,
                                  headers)
                resp = self.conn.getresponse()
                ret = (resp.status, resp.read())
            except httplib.HTTPException:
                self._close()
                raise
            except socket.error:
                self._close()
                raise

            # Close connection if in IDLE mode otherwise leave open.
            if AgentState.IDLE == self.state:
                self._close()

            return ret

    def poll(self):
        data = {
            'name': self.agent_name,
            'version': PROTOCOL_VERSION,
            'version_agent': __version__,
            'os': PLATFORM_STRING
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
                'unit': x[7],
                'warning_level': x[8],
                'critical_level': x[9],
                'lower_limit': x[10],
                'upper_limit': x[11]
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

    def __init__(self, queue, client, cmd, perf_data_opts, sampling_interval,
                 data_push_interval):
        threading.Thread.__init__(self)
        self.queue = queue
        self.client = client
        self.cmd = cmd
        self.perf_data_opts = perf_data_opts
        self.sampling_interval = sampling_interval
        self.data_push_interval = data_push_interval
        self.running = True
        self.state = AgentState.IDLE
        self.buffer = defaultdict(list)
        self.prev_sent = 0
        self.prev_recv = 0
        self.last_push = time.time()

    def __repr__(self):
        return 'task %s' % (self.cmd)

    def _next_line(self):
        output, retcode = check_output(self.cmd, shell=True)
        if retcode in [NagiosPluginExitCode.WARNING,
                       NagiosPluginExitCode.CRITICAL,
                       NagiosPluginExitCode.UNKNOWN]:
            logging.warning("plugin \"%s\" exited with code other than OK: %d "
                            "(%s)" % (self.cmd, retcode,
                                      NagiosPluginExitCode.get_name(retcode)))
        return output

    def _prepare_data(self, label):
        count = len(self.buffer[label])
        if count == 0:
            return (0, 0, 0, 0, 0, 0)

        # avg
        vmin = sys.float_info.max
        vmax = 0.0
        total = 0.0
        for v in self.buffer[label]:
            vmin = min(vmin, v)
            vmax = max(vmax, v)
            total = total + v

        avg = total / count

        # std dev
        total = 0.0
        for v in self.buffer[label]:
            total += ((v - avg) ** 2)

        stddev = 0.0
        if count > 1:
            stddev = math.sqrt((1.0 / (count - 1)) * total)

        # median
        values = sorted(self.buffer[label])
        if count % 2 == 1:
            median = values[int((count + 1) / 2 - 1)]
        else:
            lower = values[int(count / 2 - 1)]
            upper = values[int(count / 2)]
            median = (float(lower + upper)) / 2

        return (vmin, vmax, avg, stddev, median, count)

    def push_data(self, perf_data):
        for label, data in perf_data.iteritems():
            self.buffer[label].append(float(data[1]))
        if (self.last_push + self.data_push_interval) < time.time():
            try:
                for label, data in perf_data.iteritems():
                    label, value, unit, warning_level, critical_level, min_, max_ = data
                    aggregated_data = self._prepare_data(label)
                    data = (label,) + aggregated_data + (unit, warning_level,
                                                         critical_level, min_, max_)

                    try:
                        self.queue.put_nowait(data)
                    except Queue.Full:
                        pass  # Ignore data

                    self.buffer[label] = []
            except Exception:
                log_dump()
            self.last_push = time.time()

    def run(self):
        execution_time = time.time()
        while self.running:
            start = time.time()
            try:
                if AgentState.ACTIVE == self.state:
                    logging.debug('running %s ', self.cmd)
                    line = self._next_line()
                    try:
                        human_str, perf_data_str = line.split('|')
                    except ValueError:
                        perf_data_str = ''
                    perf_data_str = perf_data_str.strip()
                    perf_data = {}
                    for match in NAGIOS_PERF_DATA_REGEX.finditer(perf_data_str):
                        perf_data[match.group(1).strip()] = (match.group(1),
                                                             match.group(2),
                                                             match.group(3),
                                                             match.group(4),
                                                             match.group(5),
                                                             match.group(6),
                                                             match.group(7))
                    if len(perf_data):
                        if self.perf_data_opts and len(self.perf_data_opts) > 0:
                            for label in perf_data.keys():
                                if label in self.perf_data_opts:
                                    unit = self.perf_data_opts[label]
                                    if unit and not perf_data[label][2]:
                                        perf_data[label][2] = unit
                                else:
                                    del perf_data[label]
                        self.push_data(perf_data)
            except Exception:
                log_dump()
            execution_time += self.sampling_interval
            time.sleep(max(0.5, execution_time - start))

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
        if len(args) > 1:
            cpu_index = int(args[1], 10)
            cpu = psutil.cpu_percent(interval=1, percpu=True)
            try:
                cpu = cpu[cpu_index]
                return "CPU %d load %s%%|CPU %d=%s%%;" % (cpu_index, cpu,
                    cpu_index, cpu)
            except IndexError:
                logging.error("incorrect CPU index: %d" % cpu_index)
                return None
        else:
            cpu = psutil.cpu_percent(interval=1)
            return "CPU load %s%%|CPU=%s%%;" % (cpu, cpu)


class MemoryMetricTask(BuiltinMetricTask):
    """Built-in metric task to measure memory utilization %."""

    def _next_line_builtin(self, args):
        if hasattr(psutil, 'virtual_memory'):
            mem = psutil.virtual_memory()
        else:
            mem = psutil.phymem_usage()  # Deprecated in psutil 0.3.0 and 0.6.0
        return "Memory usage %s%% |Memusage=%s%%;" % (mem.percent,
                                                      mem.percent)


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
            counters = PsutilAdapter.net_io_counters(pernic=True)
            try:
                counters = counters[interface]
            except KeyError:
                logging.error("incorrect network interface name: "
                              "\"%s\"" % interface)
                return None
            # Format for label name in the report line below
            interface = "_" + interface
        else:
            counters = PsutilAdapter.net_io_counters(pernic=False)

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

    def __init__(self, options=None):
        self.options = options
        self.running = False
        self.state = AgentState.IDLE
        self.config = ConfigParser.ConfigParser()
        self.config.readfp(codecs.open(CONFIG_FILE, 'r', 'utf-8'))
        try:
            agent_name = self.config.get('General', 'agent_name')
            token = self.config.get('General', 'server_metrics_token')
        except ConfigParser.NoSectionError:
            logging.error("server metrics agent name (agent_name) and "
                          "token (server_metrics_token) are mandatory "
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

        self.client = ApiClient(agent_name, token, api_url, proxy_url)
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
                        cmd_args = [s for s in CONFIG_CMD_ARGS_REGEX.split(cmd)
                                    if s.strip()][1:]
                        if (not len(cmd_args) or
                            cmd_args[0].lower() not in ['cpu', 'memory',
                                                        'network', 'disk']):
                            logging.warning("unknown built-in command: \"%s\""
                                            % cmd)
                            continue

                        cmd = cmd_args[0].lower()
                        args = (self.queue, self.client, ' '.join(cmd_args),
                                None, self.sampling_interval,
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
                                            % cmd)
                    else:
                        perf_data_opts = {}
                        if self.config.has_option(section, 'performance_data'):
                            opts = self.config.get(section, 'performance_data')
                            for match in PERF_DATA_OPTS_REGEX.finditer(opts):
                                metric = (match.group(1) if match.group(1)
                                          else match.group(2))
                                perf_data_opts[metric] = match.group(3)
                        self.scheduler.add_task(Task(self.queue, self.client,
                                                     cmd, perf_data_opts,
                                                     self.sampling_interval,
                                                     self.data_push_interval))
        except Exception:
            logging.error("failed parsing commands configuration file")
            log_dump()
            sys.exit(1)

    def run(self):
        self._parse_commands()

        # In test-mode we execute all plugins and prints the output
        # to stdout. Then exist the main loop.
        if self.options and self.options.test:
            for task in self.scheduler.tasks:
                print "Command: %s" % task.cmd
                print "    %s" % task._next_line()
            return

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
                                    logging.info("switching state to %s "
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
                            new_poll_rate = int(j['poll_rate'])
                            if new_poll_rate != self.poll_rate:
                                logging.info("Switching poll rate from %s to %s."
                                        % (str(self.poll_rate), str(new_poll_rate)))
                            self.poll_rate = new_poll_rate
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
    p.add_option('-c', '--config', type='string', action='store',
                dest='config_file', default=CONFIG_FILE,
                help="Specifies the name of the config file. Default is %s." %
                    CONFIG_FILE)
    p.add_option('-D', '--no-daemon', action='store_false',
                 dest='daemon', default=True,
                 help=("When this option is specified, the server metrics "
                       "agent will not detach and does not become a daemon. "
                       "On windows this option is always enabled."))
    p.add_option('-P', '--poll-on-start', action='store_true',
                 dest='poll', default=False,
                 help=("Poll server on startup to verify connection."))
    p.add_option('--test', action='store_true',
                dest='test', default=False,
                help="Enable test mode. Runs all plugins once and then exists.")
    opts, args = p.parse_args()

    run_as_daemon = opts.daemon if running_on_linux else False
    if run_as_daemon:
        retcode = daemonize()

    CONFIG_FILE = opts.config_file

    init_logging()

    if run_as_daemon:
        logging.debug("server metrics agent daemonization returned: %d"
                      % retcode)

    if running_on_linux:
        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except IOError, e:
            logging.error("unable to write pid file \"%s\": %s" % (PID_FILE,
                                                                   repr(e)))

    if not run_as_daemon:
        print 'press Ctrl-C to stop me'

    loop = AgentLoop(opts)
    if opts.poll:
        loop.client.poll()
    loop.run()

    if not run_as_daemon:
        print 'ok ok, bye bye!'
    else:
        sys.exit(retcode)
else:
    init_logging()
