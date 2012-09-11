#!/usr/bin/env python
import ConfigParser
import sys, os, math
import subprocess, threading, time
import urllib2, json, re
import logging, logging.config, logging.handlers, traceback

try:
    import psutil
except ImportError:
    print "Can't find module psutil"
    sys.exit(1)

# need this to figure out where the config file is located
currentpath = os.path.dirname(os.path.realpath(__file__)) 

CONFIGFILE = currentpath + "/servermetrics.cfg"
VERSION = "0.04"

logging.config.fileConfig(CONFIGFILE)

def LogDump():
    tb  = str(traceback.format_exc()).split("\n")
    logging.error("")
    for i, a in enumerate(tb):
        if a.strip() != "":
            logging.error(a)
            
# json helper for ping, response will tell us if we are to be active or idle
def jsonPing(agenttoken, agentname):
    j = json.dumps({'agenttoken':agenttoken,'agentname':agentname, 'version':VERSION}, indent=4)
    return j

# json helper for data reporting
def jsonData(agenttoken,agentname,label,minValue,maxValue,avgValue,stdDevValue,medianValue,count,unit):
    j = json.dumps({'agenttoken':agenttoken,'agentname':agentname,'version':VERSION,'label':label, 'minValue':minValue, 'maxValue':maxValue, 'avgValue':avgValue, 'stdDevValue':stdDevValue,'medianValue':medianValue,'count':count, 'unit': unit}, indent=4)
    return j
    
# json http helper
def getUrl(url, jsondata):
    logging.debug(url)
    try:
        request = urllib2.Request(url, jsondata, {'Content-Type': 'application/json'})           
        response = urllib2.urlopen(request)
        j = json.loads(response.read())
        response.close()
        logging.debug(j)
        return j
    except Exception:
        LogDump()
        pass    
    
class Scheduler:
    def __init__( self ):
        self.__tasks = []
        
    def __repr__( self ):
        rep = ''
        for task in self.__tasks:
            rep += '%s\n' % `task`
        return rep
        
    def AddTask( self, agenttoken, agentname, cmd, loopdelay, dataurl ):
        task = Task( agenttoken, agentname, cmd, loopdelay, dataurl )
        self.__tasks.append( task )
    
    def StartAllTasks( self ):
        for task in self.__tasks:
            logging.debug('starting %s', task)
            task.start()

    def SetStateAllTasks( self, state ):
        for task in self.__tasks:
            task.setState( state );
    
    def StopAllTasks( self ):
        for task in self.__tasks:
            logging.debug('stopping %s', task)
            task.stop()
            task.join()

# this is the main loop, pinging server to see if state should change between idle and active
class PingLoop( threading.Thread ):
    def __init__( self ):
        self.__loopdelay = 30   # ping every 30 sec
        self.__state = 0   # 0 - unknown, 1 - idle, 2 - reporting
        self.__running = True 
        # get config file
        config = ConfigParser.ConfigParser()
        config.read(CONFIGFILE)
        self.__agenttoken = config.get('General', 'agenttoken')
        self.__agentname = config.get('General', 'agentname')
        self.__pingurl = config.get('General', 'pingurl')
        dataurl = config.get('General', 'dataurl')
        self.__sch = Scheduler()
        # config options named 'command' are our tasks
        for section in config.sections():
            if ( config.has_option(section, 'command')):
                cmd = config.get(section, 'command')
                self.__sch.AddTask(self.__agenttoken, self.__agentname, cmd, 10, dataurl )     # 10sec 
        # start all tasks (but in idle state)
        self.__sch.StartAllTasks()
        threading.Thread.__init__( self )

    def run( self ):
        self.__runtime = time.time()
        while self.__running:
            start = time.time()
            try:
                j = getUrl( self.__pingurl, jsonPing(self.__agenttoken, self.__agentname))
                if(j['state'] != self.__state):    # state changed, stop or start reporting
                    self.__state = j['state']
                    self.__sch.SetStateAllTasks( j['state'])   # notify all tasks               
            except Exception:
                LogDump()
                pass
            self.__runtime += self.__loopdelay
            time.sleep( max( 0, self.__runtime - start ) )    

    def stop( self ):
        self.__sch.StopAllTasks()
        self.__running = False

class Task( threading.Thread ):
    def __init__( self, agenttoken, agentname, cmd, loopdelay, dataurl ):
        self.__agenttoken = agenttoken
        self.__agentname = agentname
        self.__cmd = cmd
        self.__loopdelay = loopdelay
        self.__dataurl = dataurl
        self.__running = True      # is running
        self.__state = 1        # start in idle state, will be upgraded to active on first ping
        self.__dataBuffer = []  # values
        self.__prevsent = 0
        self.__prevrecv = 0
        self.__lastReportTime = time.time()
        threading.Thread.__init__( self )

    def __repr__( self ):
        return 'task %s' % ( self.__cmd )

    def setState( self, state ):
        self.__state = state
        
    def reportData(self, label, value, unit):
        self.__dataBuffer.append(float(value))
        # more than 60 secs since last report?
        if( (self.__lastReportTime + 59) < time.time() ):
            try:
                vCount = len(self.__dataBuffer)
                # avg value
                #
                vMin = sys.float_info.max
                vMax = 0.0
                vTot = 0.0
                for v in self.__dataBuffer:
                    vMin = min(vMin, v)
                    vMax = max(vMax, v)
                    vTot = vTot + v
                
                vAvg = vTot / vCount

                # std dev value
                #
                vTot = 0.0
                for v in self.__dataBuffer:
                    vTot += ((v-vAvg)**2)
        
                vStdDev = math.sqrt((1.0/(vCount-1))*(vTot))
                   
                # median
                #
                sValues = sorted(self.__dataBuffer)
                if vCount % 2 == 1:
                    vMedian = sValues[(vCount+1)/2-1]
                else:
                    lower = sValues[vCount/2-1]
                    upper = sValues[vCount/2]
                    vMedian = (float(lower + upper)) / 2

                j = getUrl(self.__dataurl, jsonData(self.__agenttoken, self.__agentname, label, vMin, vMax, vAvg, vStdDev, vMedian, vCount, unit))
                self.__lastReportTime = time.time()
                self.__dataBuffer = []
            except Exception:
                LogDump()
                pass          
        
    def run( self ):
        self.__runtime = time.time()
        while self.__running:
            start = time.time()
            logging.debug('checking %s state is %s', self.__cmd, self.__state)
            try:
                if( self.__state == 2 ):    
                    logging.debug('running %s ', self.__cmd)
                    if (self.__cmd.lower().startswith('builtin')) :
                        line = self.runInternal(self.__cmd)
                    else :
                        c = subprocess.Popen(self.__cmd, shell=True, stdout=subprocess.PIPE)
                        line = c.stdout.next() # pray for at least one line 
                    # todo: improve this regexp
                    rex = re.match('^.*\|(.*)=([0-9.]+)([a-zA-Z%/]+)', line)
                    self.reportData(rex.group(1), rex.group(2), rex.group(3))
            except Exception:
                LogDump()
                pass        
            self.__runtime += self.__loopdelay
            time.sleep( max( 0, self.__runtime - start ) )    # try to compensate for run time

    def runInternal( self, cmd ):
        errline = "unknown 0|unknown=0%%;"
        args = [s for s in re.split("( |\\\".*?\\\"|'.*?')", cmd) if s.strip()]
        if(len(args) < 2):
            logging.error('missing argument(s) for BUILTIN: '+cmd)
            return errline
            
        if(args[1].lower() == 'cpu'):
            cpu = psutil.cpu_percent(interval=1)
            line = "CPU load %s%%|CPU=%s%%;" % ( cpu, cpu )
            return line

        if(args[1].lower() == 'memory'):
            phymem = psutil.phymem_usage()
            line = "Memory usage %s%% |Memusage=%s%%;" % (
                phymem.percent,
                phymem.percent
            )
            return line
            
        if(args[1].lower() == 'network'):
            try:
                if(len(args)>2):
                    interface = args[2].replace("'", "")
                    counters = psutil.network_io_counters(pernic=True)
                    counters = counters[interface]
                else:
                    counters = psutil.network_io_counters(pernic=False)
                sent = getattr(counters, 'bytes_sent')
                recv = getattr(counters, 'bytes_recv')
                tot = 0
                if(self.__prevsent>0):
                    tot = (sent-self.__prevsent) + (recv-self.__prevrecv)
                self.__prevsent = sent
                self.__prevrecv = recv
                line = "%s over %s sec|Network=%skB/s" % (tot, self.__loopdelay, str(int((tot/self.__loopdelay) / 1024 )))
                return line    
            except Exception:
                logging.error('possibly incorrect network interface name')
                LogDump()
                return errline

        logging.error('incorrect argument for BUILTIN: '+cmd)
        return errline

    def stop( self ):
        self.__running = False   
        
    
if __name__ == "__main__":      # if started from shell
    print 'press the Any Key to stop me'
    mainLupe = PingLoop()
    mainLupe.start()
    raw_input() # run until keypress...
    print 'ok ok'
    mainLupe.stop()
    mainLupe.join()
