li-metrics-agent.py - main module - depends on psutil

li-metrics-agent-service.py - Windows service. depends on li-metrics-agent.py and pywin32

Install as service:
python li-metrics-agent-service.py install
(note: service needs to run as a defined user, not as System)

uninstall:
python li-metrics-agent-service.py remove

start or stop service:

net start LoadImpactServerMetricsAgent
net stop LoadImpactServerMetricsAgent


Agent configuration:

li-metrics-agent.conf.sample - Sample agent configuration file, containing inline comments. The agent expects its config
file to be named "li-metrics-agent.conf" and usually be located in /etc/li-metrics-agent/


psutil:
http://code.google.com/p/psutil/

pywin32:
http://sourceforge.net/projects/pywin32/
