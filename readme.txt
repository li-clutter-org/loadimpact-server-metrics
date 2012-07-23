metricsmain.py - main module - depends on psutil

metricservice.py - Windows service. depends on metricsmain.py

Install as service:
python metricservice.py install

uninstall:
python metricservice.py remove

start or stop service:

net start metricservice
net stop metricservice

servermetrics.cfg - configuration file


