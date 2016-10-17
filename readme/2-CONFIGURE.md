Configuring
===========

Note: In this article we'll be using Ubuntu 14.04, you can follow similar steps with other Linux distributions.

Configure custom metrics using psutil
-------------------------------------

Let's create a custom metric using `psutil.virtual_memory()`. First, try it in a console to see output:
```
python
>>> import psuitl;
>>> psutil.virtual_memory()
vmem(total=1040695296L, available=972890112L, percent=6.5, used=351432704L, free=689262592L, active=261943296, inactive=47529984, buffers=11210752L, cached=272416768)

>>> mem = psutil.virtual_memory().active/1024/1024;
>>> print "Memory active %sMB |MemActive=%sMB;" % (mem,mem)
Memory active 249MB |MemActive=249MB;
```

Assuming we want to have active memory in MB, we can write a python command:

```
python -c 'import psutil; mem = psutil.virtual_memory().active/1024/1024; print "Memory active %sMB |MemActive=%sMB;" % (mem,mem)'
Memory active 249MB |MemActive=249MB;
```
The output of the command is valid nagios plugin output that is readable by the agent. Here `MemActive` is the label, `249` is the value and `MB` is the unit.

Let's update the agent's `config-file`:
```
sudo vi /usr/lib/li_metrics_agent/li_metrics_agent.conf

# li_metrics_agent.conf
[test5]
command = python -c 'import psutil; mem = psutil.virtual_memory().active; print "Memory active %sB |MemActive=%sB;" % (mem,mem)'
```
Restart agent
```
sudo initctl restart li_metrics_agent
```

Run a load test and add the new metrics to the test result page!
See [running section](3-RUN.md) for instruction how to configure a test to collect metrics from an agent and how to visualize the collected data on the test result page.

Note: instead of providing a single command we can create a python script and add a path to the command option.
We'll demonstrate that approach in the next section.

Configure custom metrics using Nagios plugins
---------------------------------------------

Let's add a standard Nagios plugin to the Server Metrics Agent installed on your server.

First install nagios plugins on your server

```
sudo apt-get install nagios-plugins 
```

Select the plugin you want to add, here we'll use `check_disk`. Find where it was installed and then run `check-disk` to see possible options:
```
$ find / -type f -name 'check_disk'
/usr/lib/nagios/plugins/check_disk

$ /usr/lib/nagios/plugins/check_disk --help
... lots of output
Examples:
 check_disk -w 10% -c 5% -p /tmp -p /var -C -w 100000 -c 50000 -p /
    Checks /tmp and /var at 10% and 5%, and / at 100MB and 50MB
 check_disk -w 100 -c 50 -C -w 1000 -c 500 -g sidDATA -r '^/oracle/SID/data.*$'
    Checks all filesystems not matching -r at 100M and 50M. The fs matching the -r regex
    are grouped which means the freespace thresholds are applied to all disks together
 check_disk -w 100 -c 50 -C -w 1000 -c 500 -p /foo -C -w 5% -c 3% -p /bar
    Checks /foo for 1000M/500M and /bar for 5/3%. All remaining volumes use 100M/50M

$ /usr/lib/nagios/plugins/check_http --help
... lots of output
Examples:
 CHECK CONTENT: check_http -w 5 -c 10 --ssl -H www.verisign.com

```

Let's run the commands we need so we can see output format:
```
$ /usr/lib/nagios/plugins/check_disk -w 10% -c 5% -p /
DISK OK - free space: / 6603 MB (88% inode=88%);| /=896MB;7131;7527;0;7924

$ /usr/lib/nagios/plugins/check_http -H --ssl loadimpact.com
HTTP OK: HTTP/1.1 301 Moved Permanently - 364 bytes in 0.186 second response time |time=0.186482s;;;0.000000 size=364B;;;0
```
The output of a command is valid nagios plugin output that is readable by the agent. Here `time` and `size` are labels, `s` and `B` are units.

Open agent config file:
```
vi /usr/lib/li_metrics_agent/li_metrics_agent.conf
```

Add commands to the agent config file (we assume we have 4 predefined metrics by default):
```
# /usr/lib/li_metrics_agent/li_metrics_agent.conf
[test5]
command = /usr/lib/nagios/plugins/check_disk -w 10% -c 5% -p /
performance_data = /:MB

[test6]
command = /usr/lib/nagios/plugins/check_http -H --ssl loadimpact.com
performance_data = time:s size:B
```

Restart agent:
```
sudo initctl restart li_metrics_agent
```

Now when you run Load Impact tests you can see that 3 new metrics ("/", "time" and "size") have appeared.

### Fine tuning: custom metric names

We can change the metric name by using the `sed` command. In its simplest form, you can change one name to another name using the following syntax:
```
sed 's/old_metric_name/new_metric_name/'
```

We can also put the custom metric commands in a `disk-metric.sh` bash script

```
sudo vi /usr/local/bin/disk-metric.sh
```
and place customized output there:
```bash
#!/bin/bash
/usr/lib/nagios/plugins/check_disk -w 10% -c 5% -p / | sed 's/\/\=/Disk\ usage\=/'
```

```
sudo vi /usr/local/bin/li-http-metric.sh
```

```bash
#!/bin/bash
/usr/lib/nagios/plugins/check_http -H --ssl loadimpact.com | sed 's/time=/LI\ http\ time\=/' | sed 's/size=/LI\ http\ size\=/'  
```


Now change the folowing lines in the agent config file:
```
[test5]
command = bash disk-metric.sh
performance_data = 'Disk usage':MB

[test6]
command = bash li-http-metric.sh
performance_data = 'LI http time':s 'LI http size':B
```

Restart `li_metrics_agent` service.
```
sudo initctl restart li_metrics_agent
```

Run a load test and add the new metrics to the test result page!
See [running section](3-RUN.md) for instruction how to configure a test to collect metrics from an agent and how to visualize the collected data on the test result page.

![alt tag](custom_metrics.png)
