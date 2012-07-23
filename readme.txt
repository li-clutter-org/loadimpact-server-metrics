metricsmain.py - main module - depends on psutil

metricservice.py - Windows service. depends on metricsmain.py and pywin32

Install as service:
python metricservice.py install
(note: service needs to run as a defined user, not as System)

uninstall:
python metricservice.py remove

start or stop service:

net start metricservice
net stop metricservice

servermetrics.cfg - configuration file


psutil:
http://code.google.com/p/psutil/

pywin32:
http://sourceforge.net/projects/pywin32/