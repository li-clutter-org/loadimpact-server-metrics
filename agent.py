#!/usr/bin/env python

# This is a workaround for Python versions < 3.0 to get "true division" when
# using the division operator. "true division" = float result
from __future__ import division

import base64
import ConfigParser
import httplib
import json
import logging
import logging.config
import logging.handlers
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
import urlparse

try:
    import psutil
except ImportError:
    print "Can't find module psutil"
    sys.exit(1)

# Figure out where the config file is located.
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           'servermetrics.cfg')
PROTOCOL_VERSION = "1"
AGENT_VERSION = "0.07"
AGENT_USER_AGENT_STRING = ("LoadImpactServerMetricsAgent/%s "
                           "(Load Impact; http://loadimpact.com);"
                           % AGENT_VERSION)
DEFAULT_SERVER_METRICS_API_URL = 'http://api.loadimpact.com/v2/server-metrics'
DEFAULT_POLL_RATE = 30
DEFAULT_SAMPLING_INTERVAL = 3
DEFAULT_DATA_PUSH_INTERVAL = 10


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

    def __init__(self, agent_name, api_token, api_url):
        self.agent_name = agent_name
        self.api_token = api_token
        self.parsed_api_url = urlparse.urlparse(api_url)
        self.state = AgentState.IDLE
        self.conn = None
        self.lock = threading.Lock()

    def _build_auth(self):
        return 'Basic %s' % base64.b64encode('%s:%s' % (self.api_token, ''))

    def _connect(self):
        if not self.conn:
            port = self.parsed_api_url.port if self.parsed_api_url.port else 443
            self.conn = httplib.HTTPSConnection(self.parsed_api_url.hostname,
                                                port=port)

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
                headers['Authorization'] = self._build_auth()
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
            'version_agent': AGENT_VERSION
        }
        logging.debug(json.dumps(data))
        return self._request('POST',
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps(data))

    def push(self, label, vmin, vmax, avg, stddev, median, count, unit):
        data = {
            'name': self.agent_name,
            'version': PROTOCOL_VERSION,
            'version_agent': AGENT_VERSION,
            'label': label,
            'min': vmin,
            'max': vmax,
            'avg': avg,
            'stddev': stddev,
            'median': median,
            'count': count,
            'unit': unit
        }
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


class Task(threading.Thread):
    """A task thread is responsible for collection and reporting of a single
    metric. The metric can be one of the built-in ones or a Nagios-compatible
    plugin that is executed as a sub-process.
    """

    def __init__(self, client, cmd, sampling_interval, data_push_interval):
        threading.Thread.__init__(self)
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
                vmin, vmax, avg, stddev, median, count = self._prepare_data()
                status, body = self.client.push(label, vmin, vmax, avg, stddev,
                                                median, count, unit)
                if 201 != status:
                    logging.error("%d status code returned when pushing data "
                                  "to server: \"%s\"" % (status, repr(body)))

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


class NetworkMetricTask(BuiltinMetricTask):
    """Built-in metric task to measure network utilization metrics:
        - Kbps
        - Receive/Sent bytes delta
        - Receive/Sent packets delta
        - Receive/Sent errors delta
        - Receive/Sent drop delta
    """

    def __init__(self, *args, **kwargs):
        super(NetworkMetricTask, self).__init__(*args, **kwargs)
        self.prev_recv = 0
        self.prev_sent = 0

    def _next_line_builtin(self, args):
        if len(args) > 1:
            interface = args[1].replace("'", "")
            counters = psutil.network_io_counters(pernic=True)
            try:
                counters = counters[interface]
            except KeyError:
                logging.error("incorrect network interface name: "
                              "\"%s\"" % interface)
                return None
        else:
            counters = psutil.network_io_counters(pernic=False)
        sent = counters.bytes_sent
        recv = counters.bytes_recv
        total = 0
        if self.prev_sent > 0:
            total = (sent - self.prev_sent) + (recv - self.prev_recv)
        self.prev_sent = sent
        self.prev_recv = recv
        kbps = total / self.sampling_interval / 1024
        line = ("%s over %s sec|Network=%.2fkB/s"
                % (total, self.sampling_interval, kbps))
        return line


class DiskMetricTask(BuiltinMetricTask):
    """Built-in metric task to measure disk utilization metrics:
        - IOps
        - Read/Write count delta
        - Read/Write bytes delta
        - Read/Write time delta
    """

    def __init__(self, *args, **kwargs):
        super(DiskMetricTask, self).__init__(*args, **kwargs)
        self.prev_read_count = 0
        self.prev_write_count = 0

    def _next_line_builtin(self, args):
        counters = psutil.disk_io_counters()
        read_count = counters.read_count
        write_count = counters.write_count
        total = 0
        if self.prev_read_count > 0:
            total = ((write_count - self.prev_write_count)
                     + (read_count - self.prev_read_count))
        self.prev_write_count = write_count
        self.prev_read_count = read_count
        iops = total / self.sampling_interval
        line = ("Disk IOPS %d over %s sec|Disk=%.2fIO/s"
                % (total, self.sampling_interval, iops))
        return line


class AgentLoop(object):
    """Agent main loop. Setup logging, parse config file, setup metric
    collection tasks and start scheduler.
    """

    def __init__(self):
        logging.config.fileConfig(CONFIG_FILE)

        self.running = False
        self.state = AgentState.IDLE
        self.config = ConfigParser.ConfigParser()
        self.config.read(CONFIG_FILE)
        agent_name = self.config.get('General', 'agent_name')
        api_token = self.config.get('General', 'server_metrics_api_token')
        api_url = (
            self.config.get('General', 'server_metrics_api_url')
            if self.config.has_option('General', 'server_metrics_api_url')
            else DEFAULT_SERVER_METRICS_API_URL)
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

        self.client = ApiClient(agent_name, api_token, api_url)
        self.scheduler = Scheduler()

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
                        args = (self.client, ' '.join(cmd_args),
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
                        self.scheduler.add_task(Task(cmd,
                                                     self.sampling_interval,
                                                     self.data_push_interval))
        except Exception:
            logging.error("failed parsing commands configuration file")
            log_dump()
            sys.exit(1)

    def run(self):
        self._parse_commands()

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
                        j = json.loads(body)

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
    print 'press Ctrl-C to stop me'
    loop = AgentLoop()
    loop.run()
    print 'ok ok, bye bye!'
