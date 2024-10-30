import os
import sys
import tempfile
import threading
import tkinter as tk
import ttkbootstrap as ttkb
from logging import info
from tkinter import ttk

from utils.db_data_takers import get_connections_data, get_iiko_accounts, get_saby_accounts
from utils.programm_loop import process_queue
from utils.tools import theme, title, main_windows_size


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


# Основное окно
root = ttkb.Window(themename=theme, title=title)
root.geometry(main_windows_size)
root.protocol("WM_DELETE_WINDOW", exit_program)

# Настройка иконки приложения
from gui.iiko_ikon import icon_data, app_icon
with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name
root.iconbitmap(default=temp_icon_path)
root.call('wm', 'iconphoto', root._w, app_icon)
os.remove(temp_icon_path)

# --- Создаем фреймы для размещения таблиц ---
from gui.second_windows import SABYConnectWindow, IIKOConnectWindow, SetConnectWindow
frame_iiko = ttkb.Frame(root)
frame_iiko.pack(side="left", fill="y", padx=10)

frame_saby = ttkb.Frame(root)
frame_saby.pack(side="left", fill="y", padx=10)

frame_connections = ttkb.Frame(root)
frame_connections.pack(side="right", fill="both", expand=True, padx=10)

# --- Таблица для логинов СБИС ---
saby_tree = ttk.Treeview(frame_saby, columns=("id", "login"), show='headings', height=10)
saby_tree.heading('id', text="ID")
saby_tree.column("id", width=50, anchor='center')
saby_tree.heading('login', text="СБИС Логин")
saby_tree.column("login", width=150, anchor='center')
saby_tree.pack()

# Добавляем данные в таблицу
saby_accounts = get_saby_accounts()
for account in saby_accounts:
    saby_tree.insert('', 'end', values=(account.id, account.login))
ttk.Button(frame_saby, text="Добавить аккаунт СБИС", command=lambda: SABYConnectWindow('Новый аккаунт СБИС')).pack(pady=20)

# --- Таблица для логинов IIKO ---
iiko_tree = ttk.Treeview(frame_iiko, columns=("id", "login"), show='headings', height=10)
iiko_tree.heading('id', text="ID")
iiko_tree.column("id", width=50, anchor='center')
iiko_tree.heading('login', text="IIKO Логин")
iiko_tree.column("login", width=150, anchor='center')
iiko_tree.pack()

# Добавляем данные в таблицу
iiko_accounts = get_iiko_accounts()
for account in iiko_accounts:
    iiko_tree.insert('', 'end', values=(account.id, account.login))
ttk.Button(frame_iiko, text="Добавить аккаунт IIKO", command=lambda: IIKOConnectWindow('Новый аккаунт IIKO')).pack(pady=20)

# --- Таблица для соединений ---
connections_tree = ttk.Treeview(frame_connections, columns=("id", "iiko_login", "saby_login", "status"), show='headings')
connections_tree.heading('id', text="ID")
connections_tree.column("id", width=50, anchor='center')
connections_tree.heading('iiko_login', text="IIKO Логин")
connections_tree.column("iiko_login", width=100, anchor='center')
connections_tree.heading('saby_login', text="СБИС Логин")
connections_tree.column("saby_login", width=100, anchor='center')
connections_tree.heading('status', text="Статус")
connections_tree.column("status", width=100, anchor='center')
connections_tree.pack()

# Добавляем данные в таблицу
connections = get_connections_data()
for conn in connections:
    connections_tree.insert('', 'end', values=(conn['id'], conn['iiko']['login'], conn['saby']['login'], conn['status']))
ttk.Button(frame_connections, text="Добавить соединение", command=lambda: SetConnectWindow('Новое соединение')).pack(pady=20)

# Запуск основного цикла
root.mainloop()
root.update_idletasks()
process_queue(root)
root.after(300, process_queue, root)
