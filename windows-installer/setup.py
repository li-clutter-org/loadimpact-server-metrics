from distutils.core import setup
import py2exe
 
class Target:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.version = "0.0.7"
        self.company_name = "Load Impact AB"
        self.copyright = "Load Impact AB"
        self.name = "LoadImpactServerMetricsAgent"

myservice = Target(
    description = 'Agent for server metrics',
    modules = ['li_metrics_agent_service'],
    cmdline_style='pywin32'
)

setup(
    options = {"py2exe": {"compressed": 1, "bundle_files": 3} },   
    console=['li_metrics_agent_service.py'],
    zipfile = None,
    service=[myservice]
) 
