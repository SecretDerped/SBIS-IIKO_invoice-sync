import os
import base64
import tempfile
import tkinter as tk
from tkinter import ttk
from PIL import Image
from io import BytesIO
from utils.utils import save_data, encrypt


class GUI:
    def __init__(self, root, iiko_connect, sbis_connect, icon_data, iiko_conn_path, sbis_conn_path):
        self.root = root
        self.iiko_connect = iiko_connect
        self.sbis_connect = sbis_connect
        self.iiko_conn_path = iiko_conn_path
        self.sbis_conn_path = sbis_conn_path
        self.tree = None
        self.status_label = None

        self.root.title("Соединения IIKO")
        self.root.geometry("300x380")
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

        self.iiko_icon = self.set_icon(icon_data)
        self.create_gui()

    def set_icon(self, icon_data):
        icon_data = base64.b64decode(icon_data)
        iiko_icon = Image.open(BytesIO(icon_data))

        with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
            temp_icon_file.write(icon_data)
            temp_icon_path = temp_icon_file.name

        self.root.iconbitmap(default=temp_icon_path)
        os.remove(temp_icon_path)
        return iiko_icon

    def create_gui(self):
        self.tree = ttk.Treeview(self.root, columns=("login", "status"), show='headings')
        self.tree.heading('login', text="Логин")
        self.tree.heading('status', text="Статус")
        self.tree.column("login", width=50, anchor='center')
        self.tree.column("status", width=150, anchor='center')
        self.tree.pack()

        for key in self.iiko_connect.keys():
            self.tree.insert('', 'end', values=(key,))

        ttk.Button(self.root, text="+ Добавить соединение", command=lambda: self.create_connection_window("")).pack()
        ttk.Button(self.root, text="- Удалить соединение", command=self.remove_connection).pack()

        separator = tk.Frame(self.root, height=2, bd=1, relief=tk.SUNKEN)
        separator.pack(fill=tk.X, padx=5, pady=5)

        sbis_button = ttk.Button(self.root,
                                 text="Соединение СБИС",
                                 command=lambda: self.create_connection_window("СБИС", True))
        sbis_button.pack(side=tk.TOP, padx=10, pady=10)

        self.status_label = tk.Label(self.root, text="Не подключено")
        self.status_label.pack(side=tk.TOP, padx=10, pady=10)

    def show_window(self):
        self.root.deiconify()

    def hide_window(self):
        self.root.withdraw()

    def remove_connection(self):
        selected_item = self.tree.selection()

        if selected_item:
            for line in selected_item:
                value = self.tree.item(line, 'values')[0]
                self.iiko_connect.pop(value)
                self.tree.delete(line)

            save_data(self.iiko_connect, self.iiko_conn_path)

    def create_connection_window(self, title, is_sbis=False):
        add_window = tk.Toplevel(self.root)
        add_window.title(title)
        add_window.geometry("210x120")

        tk.Label(add_window, text="Логин:").pack()
        login_entry = tk.Entry(add_window)
        login_entry.pack()

        tk.Label(add_window, text="Пароль:").pack()
        password_entry = tk.Entry(add_window, show="*")
        password_entry.pack()

        error_label = tk.Label(add_window, text="", fg="red")

        def on_submit():
            login = login_entry.get()
            password = password_entry.get()

            if login and password:
                if login in self.iiko_connect:
                    error_label.config(text="Логин уже существует")
                    error_label.pack()
                    return

                self.tree.insert('', 'end', values=(login,))
                add_window.destroy()
                password_hash_string = encrypt(password)
                self.iiko_connect[login] = password_hash_string
                save_data(self.iiko_connect, self.iiko_conn_path)
            else:
                error_label.config(text="Введите пароль")
                error_label.pack()

        submit_button_text = "Добавить"

        if is_sbis:
            submit_button_text = "Сохранить"
            command_action = lambda: self.on_submit_sbis(login_entry.get(), password_entry.get(), add_window)
        else:
            command_action = on_submit

        submit_button = tk.Button(add_window, text=submit_button_text, command=command_action)
        submit_button.pack()

    def on_submit_sbis(self, login, password, window):
        if login:
            try:
                password_hash_string = encrypt(password)
                save_data({login: password_hash_string}, self.sbis_conn_path)
            except Exception as e:
                print(f"Error: {str(e)}")

        window.destroy()

    def update_iiko_status(self, login, new_status):
        for line in self.tree.get_children():
            if self.tree.item(line, 'values')[0] == login:
                self.tree.item(line, values=(login, new_status))
                break

    def update_sbis_status(self, login, status, color):
        self.status_label.config(text=f'{status}: {login}', fg=f'{color}')
