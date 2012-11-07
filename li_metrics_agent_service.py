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

import agent
import threading
import win32service
import win32serviceutil
import win32event

__author__ = "Load Impact"
__copyright__ = "Copyright 2012, Load Impact"
__license__ = "Apache License v2.0"
__version__ = "0.0.7"
__email__ = "support@loadimpact.com"


class AgentThread(threading.Thread):
    def __init__(self):
        super(AgentThread, self).__init__()
        self.agent_loop = agent.AgentLoop()

    def run(self):
        self.agent_loop.run()

    def stop(self):
        self.agent_loop.stop()


class AgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "LoadImpactServerMetricsAgent"
    _svc_display_name_ = "Load Impact server metrics agent"
    _svc_description_ = ("Agent for collecting and reporting server metrics "
                         "to loadimpact.com")

    # init service framework
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        # listen for a stop request
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcDoRun(self):
        #import servicemanager
        rc = None
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        self.agent = AgentThread()
        self.agent.start()
        # loop until the stop event fires
        while rc != win32event.WAIT_OBJECT_0:
            # block for 5 seconds and listen for a stop event
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.agent.stop()
        self.agent.join()
        win32event.SetEvent(self.hWaitStop)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(AgentService)
