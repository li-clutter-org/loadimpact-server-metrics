Installation 
============


Getting the agent token
------------------------------

- Login Load Impact Account
- Click "Monitoring" menu item, then "Setup" button and then choose "Load Impact Server Agent" (alternatively you can go to [https://app.loadimpact.com/server-agents/load-impact](https://app.loadimpact.com/server-agents/load-impact) page)
- Scroll to step 2, then copy token or generate and copy a new one

Use the same token for all agents/machines you wish to monitor. You can re-generate a new token at any time if you believe it has been compromised or distributed to someone outside your company. If you do re-generate a token, the old token will no longer be valid.

![alt tag](token.jpg)

Installing packages
---------------------

Load Impact distributes `.deb` and `.rpm` packages for Linux systems and a Windows installation package.
If you want to install the Server Metrics Agent from source see [building section](1b-BUILD.md).

Linux packages are distributed by the [packagecloud.io](https://packagecloud.io/loadimpact/server-metrics-agent) service.

Linux installation requires Python `v2.6` or `v2.7` installed on your server. 

### Ubuntu

Install the `psutil` dependency (skip this step if `psutil` has already been installed)
```
sudo apt-get install python-psutil
```

Packagecloud.io provides a setup script that manages `.deb` package installation including `https-transport` setup, setting PGP verification keys and adding a system `.list` file. You can see details [here](https://packagecloud.io/loadimpact/server-metrics-agent/install). So quick way is to download and run this script. Alternatively you can run the commands manually by following the [instructions](https://packagecloud.io/loadimpact/server-metrics-agent/install) in the `manual` tab.
```
wget https://packagecloud.io/install/repositories/loadimpact/server-metrics-agent/script.deb.sh
sudo bash script.deb.sh
```

Install last version of the package
```
sudo apt-get install li-metrics-agent
```

Run the configuration tool. You will be asked to give the agent a name and your server metrics token. The name is used for identification in the Load Impact application so it is recomended to choose a short readable name. The name and token will be written to the `config-file`. You can read about advanced configuration of Nagios and custom metrics plugins [here](2-CONFIGURE.md).

````
sudo li-metrics-agent-config
````

Output like `li_metrics_agent start/running, process XXXX` means that the agent has properly installed as a service and started correctly. It will be automatically restarted after a crash or server reboot.

You can also press the 'Check installation' button on the `https://app.loadimpact.com/server-agents/load-impact` page. If a new entry appears in the list then the agent has been succefully installed.
![alt tag](check_installation.png)


If something goes wrong it's recommended you check the `.log` file:
```
tail /var/log/li_metrics_agent.log
```

You can manage the agent as a regular Linux service
```
# Upstart systems (Ubuntu 12.04, Ubuntu 14.04)
sudo initctl status|stop|start|restart li_metrics_agent

# Systemd systems (Ubuntu 16.04)
sudo systemctl status|stop|start|restart li_metrics_agent.service
```

Next see [configuration section](2-CONFIGURE.md) for advanced agent configuration and [running section](3-RUN.md) for make test powered by agent running.


### Centos

Install the `psutil` dependency (skip this step if `psutil` has already been installed)
```
sudo yum install epel-release
sudo yum install python-psutil
```

Packagecloud.io provides a setup script that manages `.deb` package installation including `https-transport` setup, setting PGP verification keys and adding a system `.list` file. You can see details [here](https://packagecloud.io/loadimpact/server-metrics-agent/install). So quick way is to download and run this script. Alternatively you can run the commands manually by following the [instructions](https://packagecloud.io/loadimpact/server-metrics-agent/install) in the `manual` tab.
```
wget https://packagecloud.io/install/repositories/loadimpact/server-metrics-agent/script.rpm.sh
sudo bash script.rpm.sh
```

Install last version of the package
```
sudo yum install li-metrics-agent
```

Run the configuration tool. You will be asked to give the agent a name and your server metrics token. The name is used for identification in the Load Impact application so it is recomended to choose a short readable name. The name and token will be written to the `config-file`. You can read about advanced configuration of Nagios and custom metrics plugins [here](2-CONFIGURE.md).

````
sudo li-metrics-agent-config
````

You can also press the 'Check installation' button on the `https://app.loadimpact.com/server-agents/load-impact` page. If a new entry appears in the list then the agent has been succefully installed.
![alt tag](check_installation.png)


If something goes wrong it's recommended you check the `.log` file:
```
tail /var/log/li_metrics_agent.log
```

You can manage the agent as a regular Linux service
```
# Upstart systems (Centos 6)
sudo initctl status|stop|start|restart li_metrics_agent

# Systemd systems (Centos 7)
sudo systemctl status|stop|start|restart li_metrics_agent.service
```

Next see [configuration section](2-CONFIGURE.md) for advanced agent configuration and [running section](3-RUN.md) for make test powered by agent running.


### Windows

Download the [Windows installer](https://s3.amazonaws.com/loadimpact/server-metrics-agent/server-metrics-agent-1.1.1-win.amd64.exe), run it and the agent will install itself as a "Load Impact Server metrics agent" service. You can find it in the local services list after installation.

During the installation you will be asked to give the server metrics agent a name and also to provide your server metrics token. The server metrics token can be generated/found on your [https://app.loadimpact.com/server-agents/load-impact](https://app.loadimpact.com/server-agents/load-impact)

_**Note**: you must make sure the hostname api.loadimpact.com is added to the list of *trusted sites* for the agent to be able to report collected metrics back to Load Impact. See [https://www.itg.ias.edu/content/how-add-trusted-sites-internet-explorer](https://www.itg.ias.edu/content/how-add-trusted-sites-internet-explorer) for information on how to add a trusted site._

Installing, uninstalling, starting and stopping the service needs to be done as an administrator.

Install as a Windows service:
```
li_metrics_agent_service.exe --startup auto install
```
(Run `li_metrics_agent_service.exe` without arguments to see additional options)

Uninstall service:
```
li_metrics_agent_service.exe remove
```

Start or stop service:
```
sc start LoadImpactServerMetricsAgent
sc stop LoadImpactServerMetricsAgent
```

Next see [configuration section](2-CONFIGURE.md) for advanced agent configuration and [running section](3-RUN.md) for make test powered by agent running.
