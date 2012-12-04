Load Impact Server Metrics Agent
================================
The Load Impact Server Metrics Agent is a software you install on your server that will measure metrics and report them to Load Impact while running a load test at loadimpact.com. The agent is Nagios compatible and can read the performance data output of standard Nagios plugins for extended functionality. By default it will report CPU, memory, bandwidth and disk usage.

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
* psutil (0.6): [http://code.google.com/p/psutil/](http://code.google.com/p/psutil/)

### Windows
* psutil (0.6): [http://code.google.com/p/psutil/](http://code.google.com/p/psutil/)
* pywin32: [http://sourceforge.net/projects/pywin32/](http://sourceforge.net/projects/pywin32/)
* py2exe: [http://www.py2exe.org/](http://www.py2exe.org/)


Install instructions
--------------------
### Linux
There are three different ways of installing the agent on a Linux system. Depending on your distribution, some may not apply.

During the apt and deb installation processes you will be asked to give the agent a name and your server metrics token. The name is only for identification in the Load Impact interface. The server metrics token can be generated from your [account page on loadimpact.com](https://loadimpact.com/account#tokens)

#### Apt
Start by adding the Load Impact repository to your sources.list
```
echo 'deb http://packages.loadimpact.com latest main' >> /etc/apt/sources.list
```
Import the verification key
```
wget -q http://packages.loadimpact.com/pubkey.gpg -O- | sudo apt-key add -
```
Update your lists
```
apt-get update
```
And finally install the server metrics agent
```
apt-get install li-metrics-agent
```

#### .deb
Make sure you fulfill the requirements and then run
```
dpkg -i li-metrics-agent_VERSION.deb
```

#### Tar
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


### Windows
If you have the installer, run it and the server metrics agent will install itself as a service. Otherwise, see build instructions below. During the installation you will be asked to give the server metrics agent a name and also to provide your server metrics token. The server metrics token can be generated/found on your [account page on loadimpact.com](https://loadimpact.com/account#tokens)


Build instructions
------------------
### Windows
To build the Windows executable with py2exe, you first need to install python 2.7 (duh!), py2exe, psutil and pywin32.

From a CMD window, enter the windows-install directory and run makepy2exe.cmd from there.  This will create
all necessary files in windows-install/dist

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

#### Windows installer
A sample config file for InnoSetup (http://www.jrsoftware.org/isinfo.php) is included in the windows-installer directory. 


Copyright and license
---------------------

Copyright 2012 Load Impact AB

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this work except in compliance with the License.
You may obtain a copy of the License in the LICENSE file, or at:

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
