import os
import sys
import asyncio
import logging
import threading
import tkinter as tk
from queue import Queue
from cryptography.fernet import Fernet
from pystray import Icon as TrayIcon, MenuItem

from utils.job import job
from gui.gui import GUI
from gui.iiko_ikon import encoded
from utils.utils import load_data, load_config
from managers.iiko_manager import IIKOManager
from managers.sbis_manager import SBISManager


def start_async_loop(loop, event):
    asyncio.set_event_loop(loop)

    while not event.is_set():
        loop.run_forever()

    loop.close()


def process_queue():
    while not update_queue.empty():
        update_action = update_queue.get()
        update_action()

    root.after(100, process_queue)


def exit_program(the_icon):
    root.title("Выход...")

    stop_event.set()
    root.withdraw()
    the_icon.stop()
    new_loop.call_soon_threadsafe(new_loop.stop)
    thread.join()

    root.quit()
    root.destroy()
    sys.exit()


if __name__ == "__main__":
    config = load_config('config.json')

    log_level = getattr(logging, config['log_level'].upper())
    IIKO_CONN_PATH = os.path.join('cash', config['iiko_conn_path'])
    SBIS_CONN_PATH = os.path.join('cash', config['sbis_conn_path'])
    iiko_server_address = config['iiko_server_address']
    sbis_regulations_id = config['sbis_regulations_id']
    CRYPTOKEY = Fernet(config['cryptokey'].encode())

    log_path = os.path.join("cash", "application.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    console_out = logging.StreamHandler()
    file_log = logging.FileHandler(log_path, mode="w")
    logging.basicConfig(format='[%(asctime)s | %(levelname)s]: %(message)s',
                        handlers=(console_out, file_log),
                        level=log_level)

    root = tk.Tk()
    iiko_connect = load_data(IIKO_CONN_PATH)
    sbis_connect = load_data(SBIS_CONN_PATH)

    iiko = IIKOManager(iiko_connect, iiko_server_address, CRYPTOKEY)
    sbis = SBISManager(sbis_connect, CRYPTOKEY, sbis_regulations_id)

    gui = GUI(root, iiko_connect, sbis_connect, encoded, IIKO_CONN_PATH, SBIS_CONN_PATH)

    icon = TrayIcon("SBIS-IIKOnnect", gui.iiko_icon, menu=(
        MenuItem("Показать", lambda: update_queue.put(lambda: gui.show_window()), default=True),
        MenuItem("Выход", lambda: update_queue.put(lambda: exit_program(icon)))))

    root.after(100, process_queue)

    stop_event = threading.Event()
    new_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event))
    update_queue = Queue()
    thread.start()

    asyncio.run_coroutine_threadsafe(job(iiko, sbis, iiko_connect, sbis_connect, gui, stop_event, config), new_loop)

    icon.run_detached()
    root.mainloop()
