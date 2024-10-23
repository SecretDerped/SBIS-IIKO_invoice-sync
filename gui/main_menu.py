import os
import sys
import tempfile
import threading
import tkinter as tk
import ttkbootstrap as ttkb

from logging import info
from tkinter import ttk
from ttkbootstrap import INFO

from gui.connection import create_connection_window
from gui.iiko_ikon import icon_data, app_icon
from main import new_loop, thread
from utils.job import stop_event
from utils.programm_loop import update_queue, process_queue
from utils.tools import save_data, iiko_connections, theme, title, main_windows_size, load_data


def update_iiko_status(login, new_status):
    for line in tree.get_children():
        if tree.item(line, 'values')[0] == login:
            tree.item(line, values=(login, new_status))
            break


def update_sbis_status(login, status, color):
    update_queue.put(lambda: status_label.config(text=f'{status}: {login}', foreground=f'{color}'))


def remove_connection():
    selected_item = tree.selection()

    if selected_item:
        for line in selected_item:
            value = tree.item(line, 'values')[0]
            iiko_accounts_dict.pop(value)
            tree.delete(line)

        save_data(iiko_accounts_dict, iiko_connections)


def exit_program():
    stop_event.set()
    root.withdraw()
    # ��������� ��� �������� �������� ����
    for window in root.winfo_children():
        if isinstance(window, tk.Toplevel):
            window.destroy()
    # ������������� ����������� ���� �������
    new_loop.call_soon_threadsafe(new_loop.stop)
    # ���������, ��� ���������� thread.join() ��� �������� ������, ���� �� �� ��� ��������
    if thread.is_alive():
        thread.join()
    # ���� ��������� ����������� ���� �������
    new_loop.close()
    # �������� ���������� ������� � �������� ����� Tkinter'�, ����� ��������� ���������
    root.quit()

    # ������� ���������� � ���� �������� ������� ����� ��������� ����������
    for t in threading.enumerate():
        if t is threading.main_thread():
            continue  # ���������� ������� �����
        if t.is_alive():
            info(f'�������� ���������� ������: {t.name}')
            t.join()

    # ������ �������� ����������
    root.destroy()
    sys.exit()


root = ttkb.Window(themename=theme, title=title)
root.geometry(main_windows_size)
root.protocol("WM_DELETE_WINDOW", exit_program)

with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name
root.iconbitmap(default=temp_icon_path)
root.call('wm', 'iconphoto', root._w, app_icon)
os.remove(temp_icon_path)

tree = ttk.Treeview(root, columns=("login", "status"), show='headings')

tree.heading('login', text="�����")
tree.heading('status', text="������")
tree.column("login", width=90, anchor='center')
tree.column("status", width=150, anchor='center')
tree.pack(pady=5)

iiko_accounts_dict = load_data(iiko_connections)
for key in iiko_accounts_dict.keys():
    tree.insert('', 'end', values=(key,))

ttk.Button(root, text="�������� ����������", command=lambda: create_connection_window("")).pack(pady=20)
ttk.Button(root, text="������� ����������", command=remove_connection).pack(pady=5)

separator = ttkb.Separator(root)
separator.pack(fill='x', padx=5, pady=20)

sbis_button = ttk.Button(root, text="���������� ����", command=lambda: create_connection_window("����", True),
                         bootstyle=INFO)
sbis_button.pack(side=tk.TOP, padx=10, pady=10)

status_label = ttkb.Label(root, text="�� ����������")
status_label.pack(side=tk.TOP, padx=10, pady=0)

root.update_idletasks()
process_queue(root)
root.after(300, process_queue, root)
