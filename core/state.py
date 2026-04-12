# Source - https://stackoverflow.com/a
# Posted by Karol Zlot, modified by community. See post 'Timeline' for change history
# Retrieved 2026-01-09, License - CC BY-SA 4.0

from tqdm import tqdm
from time import sleep
import psutil

with tqdm(total=100, desc='cpu%', position=1) as cpubar, tqdm(total=100, desc='ram%', position=0) as rambar:
    while True:
        rambar.n = psutil.virtual_memory().percent
        cpubar.n = psutil.cpu_percent()
        rambar.refresh()
        cpubar.refresh()
        sleep(0.5)
