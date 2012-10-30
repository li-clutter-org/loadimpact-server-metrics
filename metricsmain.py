#!/usr/bin/env python

import ConfigParser
import json
import logging
import logging.config
import logging.handlers
import math
import os
import re
import subprocess
import sys
import threading
import time
import traceback

try:
    import psutil
except ImportError:
    print "Can't find module psutil"
    sys.exit(1)

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print "Can't find module requests"
    sys.exit(1)

# figure out where the config file is located
currentpath = os.path.dirname(os.path.realpath(__file__))
CONFIGFILE = currentpath + "/servermetrics.cfg"
PROTOCOLVERSION = "1"
AGENTVERSION = "0.07"

# setup logging
logging.config.fileConfig(CONFIGFILE)


def LogDump():
    tb = str(traceback.format_exc()).split("\n")
    logging.error("")
    for i, a in enumerate(tb):
        if a.strip() != "":
            logging.error(a)


def doPoll(url, agentname, token):
    logging.debug(url)
    j = json.dumps({
        'name': agentname,
        'version': PROTOCOLVERSION,
        'version_agent': AGENTVERSION
    }, indent=4)
    r = requests.post(url, data=j, auth=HTTPBasicAuth(token, ''))
    if r.status_code != 200:
        # todo: maybe log something useful...
        logging.error(r.status_code)
        raise Exception(r.json)

    print r.headers['content-type']
    print r.text
    return r.json


def doReport(url, agentname, token, label, minValue, maxValue, avgValue,
             stdDevValue, medianValue, count, unit):
    j = json.dumps({
        'name': agentname,
        'version': PROTOCOLVERSION,
        'version_agent': AGENTVERSION,
        'label': label,
        'min': minValue,
        'max': maxValue,
        'avg': avgValue,
        'stdDevValue': stdDevValue,
        'medianValue': medianValue,
        'count': count,
        'unit': unit
    }, indent=4)
    logging.debug(j)
    r = requests.put(url, data=j, auth=HTTPBasicAuth(token, ''))
    if r.status_code != 201:
        # todo: maybe log something useful...
        logging.error(r.status_code)
        raise Exception(r.json)


class Scheduler(object):
    def __init__(self):
        self.tasks = []

    def __repr__(self):
        rep = ''
        for task in self.tasks:
            rep += '%s\n' % repr(task)
        return rep

    def AddTask(self, agenttoken, agentname, cmd, loopdelay, dataurl):
        task = Task(agenttoken, agentname, cmd, loopdelay, dataurl)
        task.daemon = True
        self.tasks.append(task)

    def StartAllTasks(self):
        for task in self.tasks:
            logging.debug('starting %s', task)
            task.start()

    def SetStateAllTasks(self, state):
        for task in self.tasks:
            task.setState(state)

    def StopAllTasks(self, timeout=3):
        for task in self.tasks:
            logging.debug('stopping %s', task)
            task.stop()
            task.join(timeout=timeout)


class Task(threading.Thread):
    def __init__(self, agent_token, agent_name, cmd, interval, data_url):
        threading.Thread.__init__(self)
        self.agent_token = agent_token
        self.agent_name = agent_name
        self.cmd = cmd
        self.interval = interval
        self.data_url = data_url
        self.running = True      # is running
        self.state = 1  # start in idle state, will be upgraded to active on first ping
        self.buffer = []  # values
        self.prevsent = 0
        self.prevrecv = 0
        self.last_report_time = time.time()

    def __repr__(self):
        return 'task %s' % (self.cmd)

    def setState(self, state):
        self.state = state

    def reportData(self, label, value, unit):
        self.buffer.append(float(value))
        # more than 60 secs since last report?
        if (self.last_report_time + 10) < time.time():
            try:
                vCount = len(self.buffer)
                # avg value
                #
                vMin = sys.float_info.max
                vMax = 0.0
                vTot = 0.0
                for v in self.buffer:
                    vMin = min(vMin, v)
                    vMax = max(vMax, v)
                    vTot = vTot + v

                vAvg = vTot / vCount

                # std dev value
                #
                vTot = 0.0
                for v in self.buffer:
                    vTot += ((v - vAvg) ** 2)

                vStdDev = 0.0
                if vCount > 1:
                    vStdDev = math.sqrt((1.0 / (vCount - 1)) * vTot)

                # median
                #
                sValues = sorted(self.buffer)
                if vCount % 2 == 1:
                    vMedian = sValues[(vCount + 1) / 2 - 1]
                else:
                    lower = sValues[vCount / 2 - 1]
                    upper = sValues[vCount / 2]
                    vMedian = (float(lower + upper)) / 2

                doReport(self.data_url, self.agent_name, self.agent_token,
                         label, vMin, vMax, vAvg, vStdDev, vMedian, vCount,
                         unit)
                self.last_report_time = time.time()
                self.buffer = []
            except Exception:
                LogDump()

    def run(self):
        execution_time = time.time()
        while self.running:
            start = time.time()
            # logging.debug('checking %s state is %s', self.cmd, self.state)
            try:
                if self.state == 2:
                    logging.debug('running %s ', self.cmd)
                    if self.cmd.lower().startswith('builtin'):
                        line = self.runInternal(self.cmd)
                    else:
                        c = subprocess.Popen(self.cmd, shell=True,
                                             stdout=subprocess.PIPE)
                        line = c.stdout.next()  # pray for at least one line
                    # todo: improve this regexp
                    rex = re.match('^.*\|(.*)=([0-9.]+)([a-zA-Z%/]+)', line)
                    self.reportData(rex.group(1), rex.group(2), rex.group(3))
            except Exception:
                LogDump()
            execution_time += self.interval
            time.sleep(max(0, execution_time - start))  # try to compensate for run time

    def runInternal(self, cmd):
        errline = "unknown 0|unknown=0%%;"
        args = [s for s in re.split("( |\\\".*?\\\"|'.*?')", cmd) if s.strip()]

        if len(args) < 2:
            logging.error('missing argument(s) for BUILTIN: ' + cmd)
            return errline
        elif args[1].lower() == 'cpu':
            cpu = psutil.cpu_percent(interval=1)
            line = "CPU load %s%%|CPU=%s%%;" % (cpu, cpu)
            return line
        elif args[1].lower() == 'memory':
            phymem = psutil.phymem_usage()
            line = "Memory usage %s%% |Memusage=%s%%;" % (phymem.percent,
                                                          phymem.percent)
            return line
        elif args[1].lower() == 'network':
            try:
                if len(args) > 2:
                    interface = args[2].replace("'", "")
                    counters = psutil.network_io_counters(pernic=True)
                    counters = counters[interface]
                else:
                    counters = psutil.network_io_counters(pernic=False)
                sent = getattr(counters, 'bytes_sent')
                recv = getattr(counters, 'bytes_recv')
                tot = 0
                if self.prevsent > 0:
                    tot = (sent - self.prevsent) + (recv - self.prevrecv)
                self.prevsent = sent
                self.prevrecv = recv
                line = "%s over %s sec|Network=%skB/s" % (tot, self.interval, str(int((tot / self.interval) / 1024)))
                return line
            except Exception:
                logging.error('possibly incorrect network interface name')
                LogDump()
                return errline

        logging.error('incorrect argument for BUILTIN: ' + cmd)
        return errline

    def stop(self):
        self.running = False


def main():
    poll_rate = 30   # ping every 30 sec
    state = 0   # 0 - unknown, 1 - idle, 2 - reporting
    config = ConfigParser.ConfigParser()
    config.read(CONFIGFILE)
    agent_token = config.get('General', 'agenttoken')
    agent_name = config.get('General', 'agentname')
    ping_url = config.get('General', 'pingurl')
    data_url = config.get('General', 'dataurl')
    scheduler = Scheduler()

    # Config options named 'command' are our tasks.
    for section in config.sections():
        if config.has_option(section, 'command'):
            cmd = config.get(section, 'command')
            scheduler.AddTask(agent_token, agent_name, cmd, 10, data_url)  # 10sec

    # Start all tasks (in idle state).
    scheduler.StartAllTasks()

    execution_time = time.time()
    while True:
        start = time.time()
        try:
            # Poll server to see if we should switch state (start or stop
            # sending collected data to server) or alter poll rate.
            try:
                j = doPoll(ping_url, agent_name, agent_token)
            except Exception:
                LogDump()
                continue

            try:
                if j['state'] != state:
                    try:
                        state = int(j['state'])
                        scheduler.SetStateAllTasks(j['state'])
                        logging.debug("switching state to %d" % state)
                    except ValueError:
                        logging.error("type coercion failed: 'state' (\"%s\") "
                                      "to int" % str(j['state']))
            except KeyError:
                logging.error("'state' not found in JSON response")

            try:
                poll_rate = int(j['poll_rate'])
            except KeyError:
                logging.error("'poll_rate' not found in JSON response")
            except ValueError:
                logging.error("type coercion failed: 'poll_rate' (\"%s\") "
                              "to int" % str(j['state']))

            execution_time += max(10, min(3600, poll_rate))
            time.sleep(max(0, execution_time - start))
        except KeyboardInterrupt:
            scheduler.StopAllTasks()
            return


if __name__ == "__main__":      # if started from shell
    print 'press Ctrl-C to stop me'
    main()
    print 'ok ok, bye bye!'
