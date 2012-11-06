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
import Queue
import re
import socket
import subprocess
import sys
import threading
import time
import traceback

from collections import defaultdict
from urlparse import urlparse

try:
    import psutil
except ImportError:
    print "Can't find module psutil"
    sys.exit(1)

# Figure out where the config file is located.
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           'li_metrics_agent.conf')
PROTOCOL_VERSION = "1"
AGENT_VERSION = "0.07"
AGENT_USER_AGENT_STRING = ("LoadImpactServerMetricsAgent/%s "
                           "(Load Impact; http://loadimpact.com);"
                           % AGENT_VERSION)
DEFAULT_SERVER_METRICS_API_URL = 'http://api.loadimpact.com/v2/server-metrics'
DEFAULT_POLL_RATE = 30
DEFAULT_SAMPLING_INTERVAL = 3
DEFAULT_DATA_PUSH_INTERVAL = 10

UMASK = 0
WORKDIR = "/"
MAXFD = 1024
PIDFILE = "/var/run/li_metrics_agent.pid"

def daemonize():
    # The standard I/O file descriptors are redirected to /dev/null by default.
    if (hasattr(os, "devnull")):
        REDIRECT_TO = os.devnull
    else:
        REDIRECT_TO = "/dev/null"

    try:
        # Fork a child process so the parent can exit.  This returns control to
        # the command-line or shell.  It also guarantees that the child will not
        # be a process group leader, since the child receives a new process ID
        # and inherits the parent's process group ID.  This step is required
        # to insure that the next call to os.setsid is successful.
        pid = os.fork()
    except OSError, e:
        raise Exception, "%s [%d]" % (e.strerror, e.errno)

    if (pid == 0):	# The first child.
        # To become the session leader of this new session and the process group
        # leader of the new process group, we call os.setsid().  The process is
        # also guaranteed not to have a controlling terminal.
        os.setsid()

        # Is ignoring SIGHUP necessary?
        #
        # It's often suggested that the SIGHUP signal should be ignored before
        # the second fork to avoid premature termination of the process.  The
        # reason is that when the first child terminates, all processes, e.g.
        # the second child, in the orphaned group will be sent a SIGHUP.
        #
        # "However, as part of the session management system, there are exactly
        # two cases where SIGHUP is sent on the death of a process:
        #
        #   1) When the process that dies is the session leader of a session that
        #      is attached to a terminal device, SIGHUP is sent to all processes
        #      in the foreground process group of that terminal device.
        #   2) When the death of a process causes a process group to become
        #      orphaned, and one or more processes in the orphaned group are
        #      stopped, then SIGHUP and SIGCONT are sent to all members of the
        #      orphaned group." [2]
        #
        # The first case can be ignored since the child is guaranteed not to have
        # a controlling terminal.  The second case isn't so easy to dismiss.
        # The process group is orphaned when the first child terminates and
        # POSIX.1 requires that every STOPPED process in an orphaned process
        # group be sent a SIGHUP signal followed by a SIGCONT signal.  Since the
        # second child is not STOPPED though, we can safely forego ignoring the
        # SIGHUP signal.  In any case, there are no ill-effects if it is ignored.
        #
        # import signal           # Set handlers for asynchronous events.
        # signal.signal(signal.SIGHUP, signal.SIG_IGN)

        try:
            # Fork a second child and exit immediately to prevent zombies.  This
            # causes the second child process to be orphaned, making the init
            # process responsible for its cleanup.  And, since the first child is
            # a session leader without a controlling terminal, it's possible for
            # it to acquire one by opening a terminal in the future (System V-
            # based systems).  This second fork guarantees that the child is no
            # longer a session leader, preventing the daemon from ever acquiring
            # a controlling terminal.
            pid = os.fork()	# Fork a second child.
        except OSError, e:
            raise Exception, "%s [%d]" % (e.strerror, e.errno)

        if (pid == 0):	# The second child.
            # Since the current working directory may be a mounted filesystem, we
            # avoid the issue of not being able to unmount the filesystem at
            # shutdown time by changing it to the root directory.
            os.chdir(WORKDIR)
            # We probably don't want the file mode creation mask inherited from
            # the parent, so we give the child complete control over permissions.
            os.umask(UMASK)
        else:
            # exit() or _exit()?  See below.
            os._exit(0)	# Exit parent (the first child) of the second child.
    else:
        # exit() or _exit()?
        # _exit is like exit(), but it doesn't call any functions registered
        # with atexit (and on_exit) or any registered signal handlers.  It also
        # closes any open file descriptors.  Using exit() may cause all stdio
        # streams to be flushed twice and any temporary files may be unexpectedly
        # removed.  It's therefore recommended that child branches of a fork()
        # and the parent branch(es) of a daemon use _exit().
        os._exit(0)	# Exit parent of the first child.

    # Close all open file descriptors.  This prevents the child from keeping
    # open any file descriptors inherited from the parent.  There is a variety
    # of methods to accomplish this task.  Three are listed below.
    #
    # Try the system configuration variable, SC_OPEN_MAX, to obtain the maximum
    # number of open file descriptors to close.  If it doesn't exists, use
    # the default value (configurable).
    #
    # try:
    #    maxfd = os.sysconf("SC_OPEN_MAX")
    # except (AttributeError, ValueError):
    #    maxfd = MAXFD
    #
    # OR
    #
    # if (os.sysconf_names.has_key("SC_OPEN_MAX")):
    #    maxfd = os.sysconf("SC_OPEN_MAX")
    # else:
    #    maxfd = MAXFD
    #
    # OR
    #
    # Use the getrlimit method to retrieve the maximum file descriptor number
    # that can be opened by this process.  If there is not limit on the
    # resource, use the default value.
    #
    import resource		# Resource usage information.
    maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if (maxfd == resource.RLIM_INFINITY):
        maxfd = MAXFD
  
    # Iterate through and close all file descriptors.
    for fd in range(0, maxfd):
        try:
            os.close(fd)
        except OSError:	# ERROR, fd wasn't open to begin with (ignored)
            pass

    # Redirect the standard I/O file descriptors to the specified file.  Since
    # the daemon has no controlling terminal, most daemons redirect stdin,
    # stdout, and stderr to /dev/null.  This is done to prevent side-effects
    # from reads and writes to the standard I/O file descriptors.

    # This call to open is guaranteed to return the lowest file descriptor,
    # which will be 0 (stdin), since it was closed above.
    os.open(REDIRECT_TO, os.O_RDWR)	# standard input (0)

    # Duplicate standard input to standard output and standard error.
    os.dup2(0, 1)			# standard output (1)
    os.dup2(0, 2)			# standard error (2)

    return(0)



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
            'version_agent': AGENT_VERSION
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
                'version_agent': AGENT_VERSION,
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
            for i in range(0, 10):
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
        try:
            logging.config.fileConfig(CONFIG_FILE)
        except ConfigParser.NoSectionError:
            # We ignore any parsing error of logging configuration variables.
            pass

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
        self.queue = Queue.Queue()

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
    retcode = daemonize()
    fp = open(PIDFILE, "w")
    fp.write(str(os.getpid()))
    close(fp)
    print 'press Ctrl-C to stop me'
    loop = AgentLoop()
    loop.run()
    print 'ok ok, bye bye!'
    sys.exit(retcode)
