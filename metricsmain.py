#!/usr/bin/env python
import ConfigParser
import json
import re
import subprocess
import sys
import threading
import time
import urllib2
import inspect
import os
import logging
import logging.handlers

# need this to figure out where the config file is located
currentpath = os.path.dirname(inspect.currentframe().f_code.co_filename)

# todo: proper logs and log levels
LOGFILE   = currentpath  + "/metricservice.log"

logger = logging.getLogger('metricsmain')
logger.setLevel(logging.DEBUG)
handler = logging.handlers.RotatingFileHandler(LOGFILE, maxBytes=0, backupCount=0)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

def LogDump(filename):
    tb  = str(traceback.format_exc()).split("\n")
    logger.error("")
    for i, a in enumerate(tb):
        if a.strip() != "":
            logger.error(a)
            
# json helper
# report one value, perhaps we should buffer and report several values on next ping?
def fakeJson(agentname,label,value,unit):
    j = json.dumps({'clientid':agentname,'metrics':({'label':label, 'value':value, 'unit': unit},)}, indent=4)
    return j

# json http helper
# todo: could use some error handling :)
def getUrl(url, jsondata):
    logger.debug(url)
    request = urllib2.Request(url, jsondata, {'Content-Type': 'application/json'})           
    response = urllib2.urlopen(request)
    j = json.loads(response.read())
    response.close()
    logger.debug(j)
    return j
    
class Scheduler:
    def __init__( self ):
        self.__tasks = []
        
    def __repr__( self ):
        rep = ''
        for task in self.__tasks:
            rep += '%s\n' % `task`
        return rep
        
    def AddTask( self, agentname, cmd, loopdelay, dataurl ):
        task = Task( agentname, cmd, loopdelay, dataurl )
        self.__tasks.append( task )
    
    def StartAllTasks( self ):
        for task in self.__tasks:
            logger.debug('starting %s', task)
            task.start()

    def PauseAllTasks( self, state ):
        for task in self.__tasks:
            task.setState( state );
    
    def StopAllTasks( self ):
        for task in self.__tasks:
            logger.debug('stopping %s', task)
            task.stop()
            task.join()

class PingLoop( threading.Thread ):
    def __init__( self ):
        self.__loopdelay = 30   # ping every 30 sec
        self.__state = 0   # 0 - unknown, 1 - idle, 2 - reporting
        self.__running = 1
        # get config file
        config = ConfigParser.ConfigParser()
        config.read(currentpath + '/servermetrics.cfg')
        # todo: probably need a agent/client ID as well as a machine/host name
        self.__agentname = config.get('General', 'agentname')
        self.__pingurl = config.get('General', 'pingurl')
        dataurl = config.get('General', 'dataurl')
        self.__sch = Scheduler()
        # find all tasks, aka config options named 'command'
        for section in config.sections():
            if ( config.has_option(section, 'command')):
                cmd = config.get(section, 'command')
                self.__sch.AddTask(self.__agentname, cmd, 10, dataurl )     # 10sec 
        # start all tasks (but in idle state)
        self.__sch.StartAllTasks()
        threading.Thread.__init__( self )

    def run( self ):
        self.__runtime = time.time()
        while self.__running:
            start = time.time()
            try:
                j = getUrl( self.__pingurl, fakeJson(self.__agentname, 0,  0, 0))
                logger.debug("state is %s", j['status'])
                if(j['status'] != self.__state):    # status changed, stop or start reporting
                    self.__state = j['status']
                    self.__sch.PauseAllTasks( j['status'])                   
            except Exception:
                LogDump(LOGFILE)
                pass    # fix this later :)
            self.__runtime += self.__loopdelay
            time.sleep( max( 0, self.__runtime - start ) )    

    def stop( self ):
        self.__sch.StopAllTasks()
        self.__running = 0

class Task( threading.Thread ):
    def __init__( self, agentname, cmd, loopdelay, dataurl ):
        self.__agentname = agentname
        self.__cmd = cmd
        self.__loopdelay = loopdelay
        self.__dataurl = dataurl
        self.__running = 1
        self.__state = 1   # start in idle state, will be upgraded to active on first ping
        threading.Thread.__init__( self )

    def __repr__( self ):
        return '%s %s' % (
            self.__cmd, self.__loopdelay )

    def setState( self, state ):
        self.__state = state
        
    def run( self ):
        self.__runtime = time.time()
        while self.__running:
            start = time.time()
            logger.debug('checking %s state is %s', self.__cmd, self.__state)
            try:
                if( self.__state == 2 ):    
                    logger.debug('running %s ', self.__cmd)
                    c = subprocess.Popen(self.__cmd, shell=True, stdout=subprocess.PIPE)
                    line = c.stdout.next() # pray for at least one line 
                    # todo: improve this regexp
                    rex = re.match('^.*\|(.*)=([0-9.]+)([a-zA-Z%])', line)
                    j = getUrl(self.__dataurl, fakeJson(self.__agentname,rex.group(1), rex.group(2), rex.group(3)))
                    # maybe we should use the json data :)
            except Exception:
                LogDump(LOGFILE)
                pass        # well, yeah, eh...
            self.__runtime += self.__loopdelay
            logger.debug('sleeping %s secs', self.__runtime - start)
            time.sleep( max( 0, self.__runtime - start ) )    # kinda ugly...

    def stop( self ):
        self.__running = 0
    
if __name__ == "__main__":      # if started from shell
    mainLupe = PingLoop()
    mainLupe.start()
    raw_input() # run until keypress...
    mainLupe.stop()
    mainLupe.join()