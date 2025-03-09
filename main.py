import asyncio
import threading
from logging import info

from gui.main_menu import MainWindow
from utils.programm_loop import start_async_loop, stop_event, process_queue
from utils.tools import title, theme
from utils.job import job

def main():
    # Инициализация нового цикла и запуск потока для него
    new_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event))
    thread.start()
    info('Thread was started')

    window = MainWindow(title, theme, thread, new_loop)
    info('Created window, enable Tkinter instance')

    # Отправляем задачу в цикл событий без блокировки
    new_loop.call_soon_threadsafe(asyncio.create_task, job(window))
    info('New loop has started threadsave')

    # Обновляем очередь обработки событий
    window.root.after(300, process_queue, window.root)
    window.root.mainloop()

if __name__ == '__main__':
    main()