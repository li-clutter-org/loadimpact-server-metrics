import psutil
import sys
cpu = psutil.cpu_percent(interval=1)
line = "CPU load %s%%|'CPU load'=%s%%;" % (
    cpu, cpu
)
print line
sys.exit(0)
