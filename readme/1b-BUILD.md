Building from scratch
=====================

If you want to build server metrics agent from scratch here is some notes for you.


Files
-----

### Linux
* li\_metrics\_agent.py - main module - depends on psutil 
* li\_metrics\_agent.conf.sample - Sample agent configuration file, containing inline comments. The agent expects its config file to be named "li\_metrics\_agent.conf" and usually be located in /etc/li\_metrics\_agent/

### Windows
* li\_metrics\_agent.py - main module - depends on psutil 
* li\_metrics\_agent_service.py - Windows service wrapper. depends on li\_metrics\_agent.py and pywin32
* li\_metrics\_agent.conf.sample - Sample agent configuration file, containing inline comments. The agent expects its config file to be named "li\_metrics\_agent.conf" and be located in the same directory as the executable.

Dependencies
------------
### Linux
* psutil: [https://github.com/giampaolo/psutil](https://github.com/giampaolo/psutil)

### Windows
* psutil: [http://code.google.com/p/psutil/](http://code.google.com/p/psutil/)
* pywin32: [http://sourceforge.net/projects/pywin32/](http://sourceforge.net/projects/pywin32/)
* pyinstaller: [http://www.pyinstaller.org/](http://www.pyinstaller.org/)

#### Tar
Download [tar](https://s3.amazonaws.com/loadimpact/server-metrics-agent/li-metrics-agent_1.1.tar.gz)

Unpack the tar in a location you wish to store it with 
```
tar -xf li-metrics-agent_VERSION.tar.gz
```
You then need to manually configure a li\_metrics\_agent.conf file. You can use the li\_metrics\_agent.conf.sample as a template. The only setting you need to change in order to get started is the server\_metrics\_token. The server metrics token can be found on your [account page on loadimpact.com](https://loadimpact.com/account#tokens)

It is usually a good idea to change the name setting as well.

Install dependencies using pip.
```
pip install -r requirements.txt
```

Start the server metrics agent by running
```
python li\_metrics\_agent.py
```
If you do not want the server metrics agent to run as a daemon, use the -D flag.
```
python li\_metrics\_agent.py -D
```
If you want to specify a different config file than the default, use the -c flag.
```
python li\_metrics\_agent.py -c /path/to/config.file
```


Build instructions
------------------
### Windows
To build the Windows executable with pyinstaller, you first need to install python 2.7 (duh!), pyinstaller, psutil and pywin32 and InnoSetup.

From a CMD window, enter the windows-install directory and run makepy2exe.cmd from there.  This will create
all necessary files in windows-install/dist

Compile li\_metrics\_agent_service.py by pyinstaller then create Windows Installer exe-file by InnoSetup. A sample config file for InnoSetup (http://www.jrsoftware.org/isinfo.php) is included in the windows-installer directory. 

Installing, uninstalling, starting and stopping the service needs to be done as administrator.  

Install as a Windows service:
```
li\_metrics\_agent_service.exe --startup auto install
```
(Run li\_metrics\_agent_service.exe without arguments to see additional options)

Uninstall service:
```
li\_metrics\_agent_service.exe remove
```

Start or stop service:
```
sc start LoadImpactServerMetricsAgent
sc stop LoadImpactServerMetricsAgent
```
