li_metrics_agent.py - main module - depends on psutil

li_metrics_agent_service.py - Windows service. depends on li-metrics-agent.py and pywin32

Install as service:
python li_metrics_agent_service.py install
(note: service needs to run as a defined user, not as System)

uninstall:
python li_metrics_agent_service.py remove

start or stop service:

net start LoadImpactServerMetricsAgent
net stop LoadImpactServerMetricsAgent


Agent configuration:

li_metrics_agent.conf.sample - Sample agent configuration file, containing inline comments. The agent expects its config
file to be named "li_metrics_agent.conf" and usually be located in /etc/li_metrics_agent/


psutil:
http://code.google.com/p/psutil/

pywin32:
http://sourceforge.net/projects/pywin32/
