import asyncio
import threading

from gui.main_menu import root
from utils.job import job, stop_event
from utils.programm_loop import start_async_loop
from utils.tools import load_data


new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
thread.start()

connections = load_data()
asyncio.run_coroutine_threadsafe(job(), new_loop)

root.mainloop()
