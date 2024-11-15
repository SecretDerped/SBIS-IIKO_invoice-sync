from logging import warning

import tkinter as tk
from ttkbootstrap import PRIMARY, OUTLINE, SUCCESS
import ttkbootstrap as ttkb

from utils.db import SABYConnection, IIKOConnection, Connection, Session
from utils.db_data_takers import add_to_db, get_saby_accounts, get_iiko_accounts
from utils.tools import add_window_size, encode_password, enable_paste


class ConnectionWindow:
    def __init__(self, outer_window, title):
        self.main_window = outer_window
        self.window = ttkb.Toplevel()
        self.window.title(title)
        self.window.geometry(add_window_size)
        self.window.overrideredirect(True)  # Убирает рамку окна, включая верхнюю черную грань

        # Установка тонкой черной рамки
        self.window.config(bg='black')
        self.frame = ttkb.Frame(self.window, borderwidth=0, relief="solid")
        self.frame.pack(expand=True, fill='both', padx=1, pady=1)

        # Добавление кнопки для закрытия окна
        self.window.protocol("WM_DELETE_WINDOW", lambda: self.dismiss())
        self.close_button = ttkb.Button(self.frame, text="Отменить",
                                        command=self.window.destroy,
                                        bootstyle=(PRIMARY, OUTLINE))
        self.close_button.pack(side='top', anchor='ne', padx=5, pady=5)

        self.main_window.root.update_idletasks()
        self.window.update_idletasks()

        # Этот код нужен, чтобы окно подключения появлялось над основным при активации
        main_x = self.main_window.root.winfo_x()
        main_width = self.main_window.root.winfo_width()
        win_width = self.window.winfo_width()
        position_right = int(main_x + (main_width / 2) - (win_width / 2))

        main_y = self.main_window.root.winfo_y()
        main_height = self.main_window.root.winfo_height()
        win_height = self.window.winfo_height()
        position_down = int(main_y + (main_height / 2) - (win_height / 2))

        self.window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")

        self.window.grab_set()  # Захватываем пользовательский ввод
        self.window.bind_class("Entry", "<Control-v>", enable_paste)  # Включаем поддержкку втавки из буфера

        self.error_label = ttkb.Label(self.frame, foreground="red")  # Заранее инициализируем поле ошибки
        self.error_label.config(text="")

    def dismiss(self):
        self.window.grab_release()
        self.window.destroy()

    def on_submit(self, model, **kwargs):
        if '' in kwargs.values():
            self.error_label.config(text="Заполните все поля")
            self.error_label.pack()
            warning('Пустые поля при отправке записи в базу с помощью побочного окна.')
            return

        record = model(**kwargs)  # Создаем экземпляр модели, распаковывая args
        add_to_db(record)

        self.main_window.handle_instance()
        self.window.destroy()


class SABYConnectWindow(ConnectionWindow):
    def __init__(self, root, title):
        super().__init__(root, title)
        self.set_menu()

    def set_menu(self):
        # Поля ввода для подключения
        ttkb.Label(self.frame, text="Логин СБИС:").pack()
        sbis_login_entry = ttkb.Entry(self.frame)
        sbis_login_entry.pack()

        ttkb.Label(self.frame, text="Пароль СБИС:").pack()
        sbis_password_entry = ttkb.Entry(self.frame, show="*")
        sbis_password_entry.pack()

        ttkb.Label(self.frame, text="ID регламента СБИС:").pack()
        sbis_regulations_id_entry = ttkb.Entry(self.frame)
        sbis_regulations_id_entry.pack()

        # Оборачиваем вызов в лямбду для отложенного выполнения
        submit_button = ttkb.Button(self.frame, text="Добавить",
                                    command=lambda: self.on_submit(SABYConnection, login=sbis_login_entry.get(),
                                                                   password_hash=encode_password(
                                                                       sbis_password_entry.get()),
                                                                   regulation_id=sbis_regulations_id_entry.get()),
                                    bootstyle=SUCCESS)
        submit_button.pack(pady=5)


class IIKOConnectWindow(ConnectionWindow):
    def __init__(self, root, title):
        super().__init__(root, title)
        self.set_menu()

    def set_menu(self):
        # Поля ввода для подключения
        ttkb.Label(self.frame, text="Логин IIKO:").pack()
        iiko_login_entry = ttkb.Entry(self.frame)
        iiko_login_entry.pack()

        ttkb.Label(self.frame, text="Пароль IIKO:").pack()
        iiko_password_entry = ttkb.Entry(self.frame, show="*")
        iiko_password_entry.pack()

        ttkb.Label(self.frame, text="URL сервера IIKO:").pack()
        iiko_server_url_entry = ttkb.Entry(self.frame)
        iiko_server_url_entry.pack()

        submit_button = ttkb.Button(self.frame, text="Добавить",
                                    command=lambda: self.on_submit(IIKOConnection, login=iiko_login_entry.get(),
                                                                   password_hash=encode_password(
                                                                       iiko_password_entry.get()),
                                                                   server_url=iiko_server_url_entry.get()),
                                    bootstyle=SUCCESS)
        submit_button.pack(pady=5)


class SetConnectWindow(ConnectionWindow):
    def __init__(self, root, title):
        super().__init__(root, title)
        self.set_menu()

    def set_menu(self):
        # Поля ввода для подключения
        ttkb.Label(self.frame, text="Выберите аккаунт IIKO:").pack()
        # Получаем пары (id, login) для аккаунтов IIKO
        iiko_accounts = [(conn.id, conn.login) for conn in get_iiko_accounts()]
        iiko_select_field = ttkb.Combobox(self.frame, values=[login for _, login in iiko_accounts])
        iiko_select_field.pack()

        ttkb.Label(self.frame, text="Выберите аккаунт СБИС:").pack()
        # Получаем пары (id, login) для аккаунтов СБИС
        sbis_accounts = [(conn.id, conn.login) for conn in get_saby_accounts()]
        sbis_select_field = ttkb.Combobox(self.frame, values=[login for _, login in sbis_accounts])
        sbis_select_field.pack()

        submit_button = ttkb.Button(
            self.frame,
            text="Добавить",
            command=lambda: self.on_submit(
                Connection,
                saby_connection_id=next((id for id, login in sbis_accounts if login == sbis_select_field.get()), None),
                iiko_connection_id=next((id for id, login in iiko_accounts if login == iiko_select_field.get()), None)
            ),
            bootstyle=SUCCESS
        )
        submit_button.pack(pady=5)


class EditRecordWindow(ConnectionWindow):
    def __init__(self, root, title, model, record):
        super().__init__(root, title)
        self.model = model
        self.record = record
        self.set_edit_menu()

    def set_edit_menu(self):
        fields = self.model.__table__.columns.keys()  # Динамически получаем все поля
        self.entries = {}

        for field in fields:
            ttkb.Label(self.frame, text=f"{field.capitalize()}:").pack()
            entry = ttkb.Entry(self.frame)
            entry.pack()
            entry.insert(0, getattr(self.record, field, ''))  # Заполняем текущим значением
            self.entries[field] = entry

        ttkb.Button(self.frame, text="Сохранить изменения", command=self.save_changes, bootstyle=SUCCESS).pack(pady=5)

    def save_changes(self):
        with Session() as session:
            try:
                record = session.query(self.model).filter_by(id=self.record.id).first()
                for field, entry in self.entries.items():
                    setattr(record, field, entry.get())  # Обновляем значения
                session.commit()
                self.main_window.handle_instance()
                self.window.destroy()
            except Exception as e:
                session.rollback()
                self.error_label.config(text=f"Ошибка: {e}")
                self.error_label.pack()
