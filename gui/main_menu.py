import os
import sys
import tempfile
import threading
import tkinter as tk
import ttkbootstrap as ttkb
from logging import info
from tkinter import ttk

from utils.db import Connection
from utils.db_data_takers import get_connections_data, Session
from utils.programm_loop import update_queue, process_queue
from utils.tools import theme, title, main_windows_size


def update_status(conn_id, new_status):
    for line in tree.get_children():
        if tree.item(line, 'values')[0] == conn_id:
            tree.item(line, values=(conn_id, new_status))
            break


def update_sbis_status(login, status, color):
    update_queue.put(lambda: status_label.config(text=f'{status}: {login}', foreground=f'{color}'))


def remove_connection():
    # Создаем сессию для выполнения запросов
    with Session() as session:
        selected_item = tree.selection()

        if selected_item:
            for line in selected_item:
                connection_id = tree.item(line, 'values')[0]
                session.delete(Connection).where(Connection.id == connection_id)
                tree.delete(line)


stop_event = threading.Event()


def exit_program():
    from main import new_loop, thread

    stop_event.set()
    root.withdraw()
    # Закрываем все открытые дочерние окна
    for window in root.winfo_children():
        if isinstance(window, tk.Toplevel):
            window.destroy()
    # Убедитесь, что вызывается thread.join() для фонового потока, если он не был завершен
    if thread.is_alive():
        thread.join()
    # Выводим информацию о всех активных потоках перед закрытием приложения
    for t in threading.enumerate():
        if t.is_alive():
            info(f'Ожидание завершения потока: {t.name}')
            t.join()

    # Останавливаем асинхронный цикл событий
    new_loop.call_soon_threadsafe(new_loop.stop)
    # Явно закрываем асинхронный цикл событий
    new_loop.close()
    # Передаем управление обратно в основной поток Tkinter'а, чтобы завершить программу
    root.quit()
    # Полное закрытие приложения
    root.destroy()
    sys.exit(0)


root = ttkb.Window(themename=theme, title=title)
root.geometry(main_windows_size)
root.protocol("WM_DELETE_WINDOW", exit_program)

from gui.iiko_ikon import icon_data, app_icon

with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name
root.iconbitmap(default=temp_icon_path)
root.call('wm', 'iconphoto', root._w, app_icon)
os.remove(temp_icon_path)

tree = ttk.Treeview(root, columns=("id", "saby_login", "iiko_login", "status"), show='headings')
tree.heading('id', text="№")
tree.column("id", width=30, anchor='center')

tree.heading('saby_login', text="СБИС")
tree.column("saby_login", width=90, anchor='center')

tree.heading('iiko_login', text="IIKO")
tree.column("iiko_login", width=90, anchor='center')

tree.heading('status', text="Статус")
tree.column("status", width=150, anchor='center')

tree.pack(pady=5)

connections = get_connections_data()
for conn in connections:
    tree.insert('', 'end', values=(conn['id'], conn['saby']['login'], conn['iiko']['login']))

from gui.connection import create_sbis_connection_window, create_iiko_connection_window, connect_accounts_window
ttk.Button(root, text="Добавить аккаунт СБИС", command=lambda: create_sbis_connection_window('Новый аккаунт СБИС')).pack(pady=20)
ttk.Button(root, text="Добавить аккаунт IIKO", command=lambda: create_iiko_connection_window()).pack(pady=20)
ttk.Button(root, text="Добавить соединение", command=lambda: connect_accounts_window()).pack(pady=20)
ttk.Button(root, text="Удалить соединение", command=remove_connection).pack(pady=5)

separator = ttkb.Separator(root)
separator.pack(fill='x', padx=5, pady=20)

status_label = ttkb.Label(root, text="Не подключено")
status_label.pack(side=tk.TOP, padx=10, pady=0)

root.update_idletasks()
process_queue(root)
root.after(300, process_queue, root)