del /q /s dist\*.*
copy /y ..\li_metrics_agent.py
copy /y ..\li_metrics_agent_service.py
mkdir dist
pyinstaller --onefile li_metrics_agent_service.py
TYPE ..\li_metrics_agent.conf.sample | MORE /P > dist\li_metrics_agent.conf.sample
del li_metrics_agent.py
del li_metrics_agent_service.py