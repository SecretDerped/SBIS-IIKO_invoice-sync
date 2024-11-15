import sys
import tempfile
import threading
from logging import info, error
import tkinter as tk
import ttkbootstrap as ttkb
from tkinter import ttk
from PIL import ImageTk
from sqlalchemy import update

from utils.db import IIKOConnection, SABYConnection, Connection, Session
from utils.db_data_takers import get_connections_data, get_iiko_accounts, get_saby_accounts
from utils.programm_loop import stop_event
from utils.tools import main_windows_size
from gui.iiko_ikon import icon_data, iiko_icon
from gui.second_windows import SABYConnectWindow, IIKOConnectWindow, SetConnectWindow, EditRecordWindow


class MainWindow:
    def __init__(self, title, theme, thread, loop):
        # Основное окно
        self.root = ttkb.Window(title, theme)
        self.root.geometry(main_windows_size)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.exit_program(thread, loop))

        with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
            temp_icon_file.write(icon_data)
            temp_icon_path = temp_icon_file.name
        self.root.iconbitmap(default=temp_icon_path)
        self.app_icon = ImageTk.PhotoImage(iiko_icon)
        self.root.iconphoto(True, self.app_icon)

        self.iiko_table = None
        self.show_iiko_frame()

        self.saby_table = None
        self.show_saby_frame()

        self.conn_table = None
        self.show_connection_frame()

        self.handle_instance()

    def handle_instance(self):
        self.refresh_accounts_data(get_iiko_accounts(), self.iiko_table)
        self.refresh_accounts_data(get_saby_accounts(), self.saby_table)
        self.refresh_conn_data(get_connections_data(), self.conn_table)

    def update_status(self, conn_id, status):
        with Session() as session:
            try:
                # Обновляем статус подключения в базе данных
                session.execute(
                    update(Connection)
                    .where(Connection.id == conn_id)
                    .values(status=status)
                )
                session.commit()
                # Теперь обновим отображение статуса в GUI.
                # Вызовем метод для обновления отображения статуса в таблице
                self.refresh_conn_data(get_connections_data(), self.conn_table)

            except Exception as e:
                session.rollback()
                error(f"Ошибка при обновлении статуса подключения: {e}")
            finally:
                session.close()

    def exit_program(self, thread, loop):
        stop_event.set()
        self.root.withdraw()
        # Закрываем все открытые дочерние окна
        for window in self.root.winfo_children():
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
        loop.call_soon_threadsafe(loop.stop)
        # Явно закрываем асинхронный цикл событий
        loop.close()
        # Передаем управление обратно в основной поток Tkinter'а, чтобы завершить программу
        self.root.quit()
        # Полное закрытие приложения
        sys.exit(0)

        # Логика для обновления данных IIKO в GUI
        # Например, заново считывание данных из БД и перезагрузка виджета

    # Метод для удаления записей
    def delete_selected(self, tree, model):
        with Session() as session:
            selected_item = tree.selection()
            if not selected_item:
                return

            item_id = tree.item(selected_item[0], 'values')[0]  # Получаем id из выбранного элемента

            # Проверяем, к какой таблице относится удаляемая запись
            if model == Connection:
                # Удаляем только из Connections
                record = session.query(model).filter_by(id=item_id).first()
                if record:
                    session.delete(record)
                    session.commit()
                    self.handle_instance()
            else:
                # Удаляем запись из своей таблицы и каскадно из Connections
                record = session.query(model).filter_by(id=item_id).first()
                if record:
                    # Получаем все связанные записи из Connection и удаляем их
                    connections = session.query(Connection).filter_by(iiko_connection_id=item_id).all()
                    for conn in connections:
                        session.delete(conn)
                    session.delete(record)  # Удаляем основную запись
                    session.commit()
                    self.handle_instance()

    @staticmethod
    def refresh_accounts_data(accounts, tree):
        tree.delete(*tree.get_children())  # Очистка дерева
        for account in accounts:
            tree.insert('', 'end', values=(account.id, account.login))

    def edit_record(self, tree, model, title):
        selected_item = tree.selection()
        if not selected_item:
            return

        item_id = tree.item(selected_item[0], 'values')[0]  # Получаем ID записи
        with Session() as session:
            record = session.query(model).filter_by(id=item_id).first()
            if record:
                EditRecordWindow(self, title, model, record)

    def show_iiko_frame(self):
        frame_iiko = ttkb.Frame(self.root)
        frame_iiko.pack(side="left", fill="y", padx=10)

        # --- Таблица для логинов IIKO ---
        iiko_tree = ttk.Treeview(frame_iiko, columns=("id", "login"), show='headings', height=10)
        iiko_tree.heading('id', text="ID")
        iiko_tree.column("id", width=30, anchor='center')
        iiko_tree.heading('login', text="IIKO Логин")
        iiko_tree.column("login", width=150, anchor='center')
        iiko_tree.pack()

        self.iiko_table = iiko_tree
        ttk.Button(frame_iiko, text='Добавить аккаунт IIKO',
                   command=lambda: IIKOConnectWindow(self, 'Новый аккаунт IIKO')).pack(pady=5)
        tk.Button(frame_iiko, text='Редактировать выбранный аккаунт IIKO',
                  command=lambda: self.edit_record(self.iiko_table, IIKOConnection, 'Редактировать аккаунт IIKO')).pack(
            pady=5)
        ttk.Button(frame_iiko, text='Удалить выбранные аккаунты IIKO',
                   command=lambda: self.delete_selected(self.iiko_table, IIKOConnection)).pack(pady=5)

    def show_saby_frame(self):
        frame_saby = ttkb.Frame(self.root)
        frame_saby.pack(side="left", fill="y", padx=10)

        # --- Таблица для логинов СБИС ---
        saby_tree = ttk.Treeview(frame_saby, columns=("id", "login"), show='headings', height=10)
        saby_tree.heading('id', text="ID")
        saby_tree.column("id", width=30, anchor='center')
        saby_tree.heading('login', text="СБИС Логин")
        saby_tree.column("login", width=150, anchor='center')
        saby_tree.pack()

        self.saby_table = saby_tree
        ttk.Button(frame_saby, text='+ СБИС аккаунт',
                   command=lambda: SABYConnectWindow(self, 'Новый аккаунт СБИС')).pack(pady=5)
        ttk.Button(frame_saby, text='Редактировать выбранный',
                   command=lambda: self.edit_record(self.saby_table, SABYConnection,
                                                    'Редактировать аккаунт СБИС')).pack(pady=5)
        ttk.Button(frame_saby, text='Удалить выбранный',
                   command=lambda: self.delete_selected(self.saby_table, SABYConnection)).pack(pady=5)

    @staticmethod
    def refresh_conn_data(accounts, tree):
        tree.delete(*tree.get_children())  # Очистка дерева
        for account in accounts:
            tree.insert('', 'end', values=(account['id'],
                                           account['iiko']['login'],
                                           account['saby']['login'],
                                           account['status']))

    def show_connection_frame(self):
        frame_connections = ttkb.Frame(self.root)
        frame_connections.pack(side="right", fill="both", expand=True, padx=10)

        # --- Таблица для соединений ---
        connections_tree = ttk.Treeview(frame_connections, columns=("id", "iiko_login", "saby_login", "status"),
                                        show='headings')
        connections_tree.heading('id', text="ID")
        connections_tree.column("id", width=30, anchor='center')
        connections_tree.heading('iiko_login', text="IIKO Логин")
        connections_tree.column("iiko_login", width=100, anchor='center')
        connections_tree.heading('saby_login', text="СБИС Логин")
        connections_tree.column("saby_login", width=100, anchor='center')
        connections_tree.heading('status', text="Статус")
        connections_tree.column("status", width=200, anchor='center')
        connections_tree.pack()

        self.conn_table = connections_tree
        ttk.Button(frame_connections, text="Соединение +",
                   command=lambda: SetConnectWindow(self, 'Новое соединение')).pack(pady=5)
        ttk.Button(frame_connections, text="Удалить выбранное",
                   command=lambda: self.delete_selected(self.conn_table, Connection)).pack(pady=5)
        ttk.Button(frame_connections, text='Редактировать',
                   command=lambda: self.edit_record(self.conn_table, Connection, 'Редактировать соединение')).pack(
            pady=5)

        self.refresh_conn_data(get_connections_data(), self.conn_table)

