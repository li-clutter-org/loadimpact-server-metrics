Running
=======

First you should attach an installed agent to the test. Go to test configuration page, scroll down to the `Server monitoring` panel and add an agent to the test configuration. Then save the test config by pressing the button on the top of the page.

![alt tag](check_installation.png)

Now the test is ready to be run and collect metrics from attached agent(s). Press the `Run test` button on the top of the page and see test running. You will see something like

```
Waiting for server agents...
last-u14 agent online 100%
* last-u14 online
```

in the progress panel, then you know the agent works fine. While the test is running and after it has finished you can add metrics collected by the agent to the dashboard. Four metrics are collected by default: Network, CPU, Memusage, Disk). If you want to add more see [configuration section](2-CONFIGURE.md).

![alt tag](add_visualization.png)

Now you can add any of the collected server metrics on your dashboard.

![alt tag](intro.png)
