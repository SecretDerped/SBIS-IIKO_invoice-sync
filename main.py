import asyncio
import threading

from gui.main_menu import iiko_accounts_dict, root
from utils.job import job, stop_event
from utils.programm_loop import start_async_loop
from utils.tools import saby_connections, load_data


new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
thread.start()

sbis_connect = load_data(saby_connections)
asyncio.run_coroutine_threadsafe(job(iiko_accounts_dict, sbis_connect), new_loop)

root.mainloop()
