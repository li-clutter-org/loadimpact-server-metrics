## Windows installer building notes

#### 1. Download distributives

- python-2.7.12.amd64.msi
- pywin32-220.win-amd64-py2.7.exe
- innosetup-5.5.9-unicode.exe

#### 2. Launch windows server

- place distributives into shared folder


#### 3. Install python and libs

- copy distributives to Downloads folder
- install python (click on distributive)
- install pywin32 (click on distributive as Administrator)
- open cmd
- set PATH=%PATH%;C:\Python27;C:\Python27\Scripts
- install innosetup

#### Prepare files

- copy `li_metrics_agent.conf.sample` to `windows-installer`
- set `windows` line endings for `windows-installer/li_metrics_agent.conf.sample`
- copy `li_metrics_agent_service.py` to `windows-installer`
- copy `li_metrics_agent.py` to  `windows-installer`
- copy `windows installer` to windows server

- pyinstaller --onefile li_metrics_agent_service.py
- see result `./dist/li_metrics_agent_service.exe`

- run innodb script
- see result in `/Output` folder



a054e6945f8090ecd11483ab9e8a40936e0094b7454139ca4a42b14fe1d9ee9d