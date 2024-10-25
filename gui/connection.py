from ttkbootstrap import PRIMARY, OUTLINE, SUCCESS

from gui.main_menu import root, connections, status_label, tree
from gui.windows import add_mouse_moving_trait
import ttkbootstrap as ttkb

from utils.tools import add_window_size, cryptokey, save_data, iiko_connections, saby_connections


def create_connection_window(title, is_sbis=False):
    add_window = ttkb.Toplevel(root)
    add_window.title(title)
    add_window.geometry(add_window_size)
    add_window.overrideredirect(True)  # Убирает рамку окна, включая верхнюю черную грань

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

    add_window.protocol("WM_DELETE_WINDOW", add_window.destroy())

    # Добавление кнопки для закрытия окна
    close_button = ttkb.Button(inner_frame, text="X", command=add_window.destroy, bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top', anchor='ne', padx=5, pady=5)

    ttkb.Label(inner_frame, text="Логин:").pack()
    login_entry = ttkb.Entry(inner_frame)
    login_entry.pack()

    ttkb.Label(inner_frame, text="Пароль:").pack()
    password_entry = ttkb.Entry(inner_frame, show="*")
    password_entry.pack()

    error_label = ttkb.Label(inner_frame, foreground="red")

    def on_submit():
        login = login_entry.get()
        password = password_entry.get()

        if login and password:
            if login in connections:
                error_label.config(text="Логин уже существует")
                error_label.pack()
                return

            tree.insert('', 'end', values=(login,))
            add_window.destroy()
            password_hash_string = cryptokey.encrypt(password.encode()).decode()
            connections[login] = password_hash_string
            save_data(connections, iiko_connections)

        else:
            error_label.config(text="Введите пароль")
            error_label.pack()

    def on_submit_sbis(login, password, window):
        if login:
            try:
                sbis.auth(login, password)
                status_label.config(text=f'? Подключено: {login}', foreground="green")

            except Exception:
                status_label.config(text=f'(!) Ошибка: {login}', foreground="red")

            password_hash_string = cryptokey.encrypt(password.encode()).decode()
            login_data = {'login': password_hash_string}
            save_data(login_data, saby_connections)

        window.destroy()

    submit_button_text = "Добавить"

    if is_sbis:
        submit_button_text = "Сохранить"
        command_action = lambda: on_submit_sbis(login_entry.get(), password_entry.get(), add_window)
    else:
        command_action = on_submit

    submit_button = ttkb.Button(inner_frame, text=submit_button_text, command=command_action, bootstyle=SUCCESS)
    submit_button.pack(pady=5)

    # Центрирование окна
    root.update_idletasks()
    main_width = root.winfo_width()
    main_height = root.winfo_height()
    main_x = root.winfo_x()
    main_y = root.winfo_y()

    add_window.update_idletasks()
    win_width = add_window.winfo_width()
    win_height = add_window.winfo_height()

    position_right = int(main_x + (main_width / 2) - (win_width / 2))
    position_down = int(main_y + (main_height / 2) - (win_height / 2))

    add_window.geometry(f"{win_width}x{win_height}+{position_right}+{position_down}")