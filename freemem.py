import psutil
import sys

phymem = psutil.phymem_usage()
buffers = getattr(psutil, 'phymem_buffers', lambda: 0)()
cached = getattr(psutil, 'cached_phymem', lambda: 0)()
used = phymem.total - (phymem.free + buffers + cached)
line = "Memory usage %6s/%s |Memusage=%s%%;" % (

    str(int(used / 1024 / 1024)) + "M",
    str(int(phymem.total / 1024 / 1024)) + "M",
    phymem.percent
)
print line
sys.exit(0)
