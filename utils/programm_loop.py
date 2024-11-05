import asyncio
from threading import Event
from asyncio import Queue
from ttkbootstrap import Window


update_queue = Queue()
stop_event = Event()


def start_async_loop(loop, event):
    asyncio.set_event_loop(loop)
    while not event.is_set():
        loop.run_forever()
    loop.close()


def process_queue(window: Window):
    while not update_queue.empty():
        update_queue.get()
    window.after(300, process_queue, window)
