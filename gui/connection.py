from ttkbootstrap import PRIMARY, OUTLINE, SUCCESS
from gui.main_menu import root, tree
from gui.windows import add_mouse_moving_trait
import ttkbootstrap as ttkb

from utils.db import SABYConnection, IIKOConnection, Connection
from utils.db_data_takers import add_to_db, get_saby_accounts, get_iiko_accounts
from utils.tools import add_window_size, encode_password


def dismiss(window):
    window.grab_release()
    window.destroy()


def SBIS_connect_menu(frame):
    # Поля ввода для подключения
    ttkb.Label(frame, text="Логин СБИС:").pack()
    sbis_login_entry = ttkb.Entry(frame)
    sbis_login_entry.pack()

    ttkb.Label(frame, text="Пароль СБИС:").pack()
    sbis_password_entry = ttkb.Entry(frame, show="*")
    sbis_password_entry.pack()

    ttkb.Label(frame, text="ID регламента СБИС:").pack()
    sbis_regulations_id_entry = ttkb.Entry(frame)
    sbis_regulations_id_entry.pack()

    return {'login': sbis_login_entry,
            'password': sbis_password_entry,
            'reg_id': sbis_regulations_id_entry}


def IIKO_connect_menu(frame):
    # Поля ввода для подключения
    ttkb.Label(frame, text="Логин IIKO:").pack()
    iiko_login_entry = ttkb.Entry(frame)
    iiko_login_entry.pack()

    ttkb.Label(frame, text="Пароль IIKO:").pack()
    iiko_password_entry = ttkb.Entry(frame, show="*")
    iiko_password_entry.pack()

    ttkb.Label(frame, text="URL сервера IIKO:").pack()
    iiko_server_url_entry = ttkb.Entry(frame)
    iiko_server_url_entry.pack()

    return {'login': iiko_login_entry,
            'password': iiko_password_entry,
            'server_url': iiko_server_url_entry}


def connection_menu(frame):
    # Поля ввода для подключения
    ttkb.Label(frame, text="Выберите аккаунт IIKO:").pack()
    iiko_accounts = [conn.iiko_connection.login for conn in get_iiko_accounts()]
    iiko_select_field = ttkb.Combobox(frame, values=iiko_accounts)
    iiko_select_field.pack()

    ttkb.Label(frame, text="Выберите аккаунт СБИС:").pack()
    sbis_accounts = [conn.saby_connection.login for conn in get_saby_accounts()]
    sbis_select_field = ttkb.Combobox(frame, values=sbis_accounts)
    sbis_select_field.pack()

    return {'iiko_acc': iiko_select_field,
            'sbis_acc': sbis_select_field}


def create_sbis_connection_window(title):
    add_window = ttkb.Toplevel()
    add_window.title(title)
    add_window.geometry(add_window_size)
    # Добавление кнопки для закрытия окна
    add_window.protocol("WM_DELETE_WINDOW", lambda: dismiss(add_window))
    # Убирает рамку окна, включая верхнюю черную грань
    add_window.overrideredirect(True)
    # Установка тонкой черной рамки
    add_window.config(bg='black')
    inner_frame = ttkb.Frame(add_window,
                             borderwidth=0,
                             relief="solid")
    inner_frame.pack(expand=True,
                     fill='both',
                     padx=1,
                     pady=1)

    close_button = ttkb.Button(inner_frame,
                               text="Отменить",
                               command=add_window.destroy,
                               bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top',
                      anchor='ne',
                      padx=5,
                      pady=5)

    account = SBIS_connect_menu(inner_frame)

    error_label = ttkb.Label(inner_frame, foreground="red")

    def on_submit():
        login = account.get('login')
        password = account.get('password')
        reg_id = account.get('reg_id')

        if not (login and
                password and
                reg_id):
            error_label.config(text="Все поля должны быть заполнены")
            error_label.pack()

        tree.insert('', 'end', values=login)

        add_window.destroy()
        sbis = SABYConnection(login=login,
                              password_hash=encode_password(password),
                              regulation_id=reg_id)
        add_to_db(sbis)

    submit_button = ttkb.Button(inner_frame,
                                text="Добавить",
                                command=on_submit,
                                bootstyle=SUCCESS)
    submit_button.pack(pady=5)

    # Центрирование окна
    root.update_idletasks()
    main_width = root.winfo_width()
    main_height = root.winfo_height()
    main_x = root.winfo_x()
    main_y = root.winfo_y()
    # Этот код нужен, чтобы окно подключения появлялся над основным при активации
    add_window.update_idletasks()
    win_width = add_window.winfo_width()
    win_height = add_window.winfo_height()
    position_right = int(main_x + (main_width / 2) - (win_width / 2))
    position_down = int(main_y + (main_height / 2) - (win_height / 2))
    add_window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")
    add_window.grab_set()       # захватываем пользовательский ввод


def create_iiko_connection_window():
    add_window = ttkb.Toplevel(root)
    add_window.title('Новый аккаунт IIKO')
    add_window.geometry(add_window_size)
    add_window.protocol("WM_DELETE_WINDOW", lambda: dismiss(add_window))
    # Убирает рамку окна, включая верхнюю черную грань
    add_window.overrideredirect(True)
    # Установка тонкой черной рамки
    add_window.config(bg='black')
    inner_frame = ttkb.Frame(add_window,
                             borderwidth=0,
                             relief="solid")
    inner_frame.pack(expand=True,
                     fill='both',
                     padx=1,
                     pady=1)
    add_mouse_moving_trait(inner_frame)

    close_button = ttkb.Button(inner_frame,
                               text="X",
                               command=add_window.destroy,
                               bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top',
                      anchor='ne',
                      padx=5,
                      pady=5)

    login, password, server_url = SBIS_connect_menu(inner_frame)
    error_label = ttkb.Label(inner_frame, foreground="red")

    def on_submit():
        iiko_login = login.get()
        iiko_password = password.get()
        iiko_server = server_url.get()

        if not (iiko_login and
                iiko_password and
                iiko_server):
            error_label.config(text="Все поля должны быть заполнены")
            error_label.pack()

        tree.insert('', 'end', values=iiko_login)
        add_window.destroy()
        iiko = IIKOConnection(iiko_login=iiko_login,
                              iiko_password=encode_password(iiko_password),
                              iiko_server=iiko_server)
        add_to_db(iiko)

    submit_button = ttkb.Button(inner_frame,
                                text="Добавить",
                                command=on_submit,
                                bootstyle=SUCCESS)
    submit_button.pack(pady=5)

    # Центрирование окна
    root.update_idletasks()
    main_width = root.winfo_width()
    main_height = root.winfo_height()
    main_x = root.winfo_x()
    main_y = root.winfo_y()
    # Этот код нужен, чтобы окно подключения появлялся над основным при активации
    add_window.update_idletasks()
    win_width = add_window.winfo_width()
    win_height = add_window.winfo_height()
    position_right = int(main_x + (main_width / 2) - (win_width / 2))
    position_down = int(main_y + (main_height / 2) - (win_height / 2))
    add_window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")


def connect_accounts_window():
    add_window = ttkb.Toplevel(root)
    add_window.title('Новое соединение')
    add_window.geometry(add_window_size)
    add_window.protocol("WM_DELETE_WINDOW", lambda: dismiss(add_window))
    # Убирает рамку окна, включая верхнюю черную грань
    add_window.overrideredirect(True)
    # Установка тонкой черной рамки
    add_window.config(bg='black')
    inner_frame = ttkb.Frame(add_window,
                             borderwidth=0,
                             relief="solid")
    inner_frame.pack(expand=True,
                     fill='both',
                     padx=1,
                     pady=1)
    add_mouse_moving_trait(inner_frame)

    close_button = ttkb.Button(inner_frame,
                               text="X",
                               command=add_window.destroy,
                               bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top',
                      anchor='ne',
                      padx=5,
                      pady=5)

    iiko_data, sbis_data = connection_menu(inner_frame)

    error_label = ttkb.Label(inner_frame, foreground="red")

    def on_submit():
        selected_iiko = iiko_data.get('iiko_acc')
        print(selected_iiko)
        iiko_acc_id = 0
        selected_sbis = sbis_data.get('sbis_acc')
        sbis_acc_id = 1

        if not (selected_iiko and
                selected_sbis):
            error_label.config(text="Нужны оба аккаунта")
            error_label.pack()

        #tree.insert('', 'end', values=sbis_login)

        conn = Connection(saby_connection_id=sbis_acc_id,
                          iiko_connection_id=iiko_acc_id)
        add_to_db(conn)

        add_window.destroy()

    submit_button = ttkb.Button(inner_frame,
                                text="Добавить",
                                command=on_submit,
                                bootstyle=SUCCESS)
    submit_button.pack(pady=5)

    # Центрирование окна
    root.update_idletasks()
    main_width = root.winfo_width()
    main_height = root.winfo_height()
    main_x = root.winfo_x()
    main_y = root.winfo_y()
    # Этот код нужен, чтобы окно подключения появлялся над основным при активации
    add_window.update_idletasks()
    win_width = add_window.winfo_width()
    win_height = add_window.winfo_height()
    position_right = int(main_x + (main_width / 2) - (win_width / 2))
    position_down = int(main_y + (main_height / 2) - (win_height / 2))
    add_window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")


class ConnectionWindow:
    def __init__(self, title):
        self.window = ttkb.Toplevel()
        self.window.title(title)
        self.window.geometry(add_window_size)
        # Добавление кнопки для закрытия окна
        self.window.protocol("WM_DELETE_WINDOW", lambda: dismiss())
        # Убирает рамку окна, включая верхнюю черную грань
        self.window.overrideredirect(True)
        # Установка тонкой черной рамки
        self.window.config(bg='black')
        inner_frame = ttkb.Frame(self.window,
                                 borderwidth=0,
                                 relief="solid")
        inner_frame.pack(expand=True,
                         fill='both',
                         padx=1,
                         pady=1)

        self.close_button = ttkb.Button(inner_frame,
                                        text="Отменить",
                                        command=self.window.destroy,
                                        bootstyle=(PRIMARY, OUTLINE))
        self.close_button.pack(side='top',
                          anchor='ne',
                          padx=5,
                          pady=5)

        self.account = SBIS_connect_menu(inner_frame)
        self.error_label = ttkb.Label(inner_frame, foreground="red")

        submit_button = ttkb.Button(inner_frame,
                                    text="Добавить",
                                    command=self.on_submit,
                                    bootstyle=SUCCESS)
        submit_button.pack(pady=5)
        # Центрирование окна
        root.update_idletasks()
        main_width = root.winfo_width()
        main_height = root.winfo_height()
        main_x = root.winfo_x()
        main_y = root.winfo_y()
        # Этот код нужен, чтобы окно подключения появлялся над основным при активации
        self.window.update_idletasks()
        win_width = self.window.winfo_width()
        win_height = self.window.winfo_height()
        position_right = int(main_x + (main_width / 2) - (win_width / 2))
        position_down = int(main_y + (main_height / 2) - (win_height / 2))
        self.window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")
        self.window.grab_set()  # захватываем пользовательский ввод

    def dismiss(self):
        self.window.grab_release()
        self.window.destroy()

    def on_submit(self):
        login = self.account.get('login')
        password = self.account.get('password')
        reg_id = self.account.get('reg_id')

        if not (login and
                password and
                reg_id):
            self.error_label.config(text="Все поля должны быть заполнены")
            self.error_label.pack()

        tree.insert('', 'end', values=login)

        self.window.destroy()
        sbis = SABYConnection(login=login,
                              password_hash=encode_password(password),
                              regulation_id=reg_id)
        add_to_db(sbis)
