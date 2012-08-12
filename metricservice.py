#/usr/bin/env python
import win32service
import win32serviceutil
import win32event
import metricsmain

class MetricService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ServerMetrics"
    _svc_display_name_ = "LoadImpact.com agent"
    _svc_description_ = "Agent for server metrics"

    # init service framework
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self,args)
        # listen for a stop request
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
    
    def SvcDoRun(self):
        import servicemanager
        rc = None
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        self.mainLupe = metricsmain.PingLoop()
        self.mainLupe.start()            
        # loop until the stop event fires
        while rc != win32event.WAIT_OBJECT_0:        
            # block for 5 seconds and listen for a stop event
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.mainLupe.stop()
        self.mainLupe.join()
        win32event.SetEvent(self.hWaitStop)
        
if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(MetricService)