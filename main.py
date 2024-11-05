# main.py
import asyncio
import threading

from gui.main_menu import MainWindow
from utils.db_data_takers import get_connections_data
from utils.job import job
from utils.programm_loop import start_async_loop, stop_event, process_queue
from utils.tools import title, theme

new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event))
thread.start()

# Запуск основного цикла
window = MainWindow(title, theme, thread, new_loop)
connections = get_connections_data()

# Отправляем задачу в цикл событий без блокировки
new_loop.call_soon_threadsafe(asyncio.create_task, job(connections))

# Старт основного цикла Tkinter и обновление очереди
window.root.after(300, process_queue, window.root)
window.root.mainloop()
