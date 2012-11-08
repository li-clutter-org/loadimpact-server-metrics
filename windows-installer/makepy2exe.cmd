del /q /s dist\*.*
copy /y ..\li_metrics_agent.py
copy /y ..\li_metrics_agent_service.py
xcopy /s /y redist\*.* dist
setup.py py2exe
copy ..\li_metrics_agent.conf.sample dist\li_metrics_agent.conf.sample
del /q *.py

