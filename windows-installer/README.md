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

#### 4. Build installer

- copy repo to windows server
- run `make2exe`
- see result `./dist/li_metrics_agent_service.exe`
- run innodb script
- see result in `/Output` folder
