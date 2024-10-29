import asyncio
import threading

from utils.db_data_takers import get_connections_data
from utils.job import job, stop_event
from utils.programm_loop import start_async_loop


new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
thread.start()

connections = get_connections_data()
asyncio.run_coroutine_threadsafe(job(connections), new_loop)

from gui.main_menu import root
root.mainloop()
