#/usr/bin/env python

import agent
import threading
import win32service
import win32serviceutil
import win32event


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
