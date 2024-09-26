import re
import os
import sys
import time
import json
import atexit
import base64
import hashlib
import asyncio
import logging
import requests
import tempfile
import xmltodict
import threading
import traceback
import tkinter as tk
from io import BytesIO
from queue import Queue
import ttkbootstrap as ttkb
from tkinter import ttk, font
from PIL import Image, ImageTk
from logging import info as log
from gui.iiko_ikon import encoded
from ttkbootstrap.constants import *
from cryptography.fernet import Fernet
from datetime import datetime, timedelta, date
from ttkbootstrap.toast import ToastNotification

search_doc_days = 31
log_level = logging.INFO
iiko_server_address = 'city-kids-ooo-perezagruzka-co.iiko.it'
#iiko_server_address = 'city-kids-pro-fashion-co.iiko.it'
CONCEPT_IGNORE_LIST = ['ООО "Город детей"', "Каблахова Д.А.", 'ООО "Планета-М"', "ИП Андреев И.В."]
INN_IGNORE_LIST = ['2311368256']
main_title = 'Соединения для ООО "Перезагрузка"'

SECONDS_OF_WAITING = 5
XML_FILEPATH = 'income_doc_cash.xml'
IIKO_CONN_PATH = 'iiko_cash.json'
SBIS_CONN_PATH = 'sbis_cash.json'
add_window_size = "210x230"
main_windows_size = "340x490"
error_windows_size = "440x410"
sbis_regulations_id = '129c1cc6-454c-4311-b774-f7591fcae4ff'
CRYPTOKEY = Fernet(b'fq1FY_bAbQro_m72xkYosZip2yzoezXNwRDHo-f-r5c=')

console_out = logging.StreamHandler()
file_log = logging.FileHandler(f"application.log", mode="w")
logging.basicConfig(format='[%(asctime)s] | %(message)s',
                    handlers=(file_log, console_out),
                    level=log_level)


def start_async_loop(loop, event):
    asyncio.set_event_loop(loop)

    while not event.is_set():
        loop.run_forever()

    loop.close()


def on_root_close():
    exit_program()


def exit_program():
    stop_event.set()
    root.withdraw()

    # Закрываем все открытые дочерние окна
    for window in root.winfo_children():
        if isinstance(window, tk.Toplevel):
            window.destroy()

    # Останавливаем асинхронный цикл событий
    new_loop.call_soon_threadsafe(new_loop.stop)

    # Убедитесь, что вызывается thread.join() для фонового потока, если он не был завершен
    if thread.is_alive():
        thread.join()

    # Явно закрываем асинхронный цикл событий
    new_loop.close()

    # Передаем управление обратно в основной поток Tkinter'а, чтобы завершить программу
    root.quit()

    # Выводим информацию о всех активных потоках перед закрытием приложения
    for t in threading.enumerate():
        if t is threading.main_thread():
            continue  # Игнорируем главный поток
        if t.is_alive():
            log(f'Ожидание завершения потока: {t.name}')
            t.join()

    # Полное закрытие приложения
    root.destroy()

    sys.exit()


@atexit.register
def cleanup():
    log("Завершение работы и освобождение ресурсов...")


def save_data(data, path):
    with open(path, 'w') as file:
        json.dump(data, file)


def load_data(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as file:
                return json.load(file)

        except json.decoder.JSONDecodeError:
            os.remove(path)
            return {}

    return {}


def process_queue():
    while not update_queue.empty():
        update_action = update_queue.get()
        update_action()

    root.after(400, process_queue)


def remove_connection():
    selected_item = tree.selection()

    if selected_item:
        for line in selected_item:
            value = tree.item(line, 'values')[0]
            iiko_connect.pop(value)
            tree.delete(line)

        save_data(iiko_connect, IIKO_CONN_PATH)


def show_notification(text):
    toast = ToastNotification(
        title="Уведомление SBISIIKOconnect",
        message=text,
        duration=5000,
        icon=''
    )

    toast.show_toast()


def create_connection_window(title, is_sbis=False):
    add_window = ttkb.Toplevel(root)
    add_window.title(title)
    add_window.geometry(add_window_size)
    add_window.overrideredirect(True)  # Убирает рамку окна, включая верхнюю черную грань

    # Установка тонкой черной рамки
    add_window.config(bg='black')
    inner_frame = ttkb.Frame(add_window, borderwidth=0, relief="solid")
    inner_frame.pack(expand=True, fill='both', padx=1, pady=1)

    def start_move(event):
        add_window.x = event.x
        add_window.y = event.y

    def stop_move(event):
        add_window.x = None
        add_window.y = None

    def on_move(event):
        deltax = event.x - add_window.x
        deltay = event.y - add_window.y
        x = add_window.winfo_x() + deltax
        y = add_window.winfo_y() + deltay
        add_window.geometry(f"+{x}+{y}")

    def on_add_window_close():
        add_window.destroy()

    add_window.protocol("WM_DELETE_WINDOW", on_add_window_close)

    # Привязка событий для перемещения окна
    inner_frame.bind("<ButtonPress-1>", start_move)
    inner_frame.bind("<ButtonRelease-1>", stop_move)
    inner_frame.bind("<B1-Motion>", on_move)

    # Добавление кнопки для закрытия окна
    close_button = ttkb.Button(inner_frame, text="X", command=add_window.destroy, bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top', anchor='ne', padx=5, pady=5)

    ttkb.Label(inner_frame, text="Логин:").pack()
    login_entry = ttkb.Entry(inner_frame)
    login_entry.pack()

    ttkb.Label(inner_frame, text="Пароль:").pack()
    password_entry = ttkb.Entry(inner_frame, show="*")
    password_entry.pack()

    error_label = ttkb.Label(inner_frame, text="", foreground="red")

    def on_submit():
        login = login_entry.get()
        password = password_entry.get()

        if login and password:
            if login in iiko_connect:
                error_label.config(text="Логин уже существует")
                error_label.pack()
                return

            tree.insert('', 'end', values=(login,))
            add_window.destroy()
            password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
            iiko_connect[login] = password_hash_string
            save_data(iiko_connect, IIKO_CONN_PATH)

        else:
            error_label.config(text="Введите пароль")
            error_label.pack()

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


def validate_supplier(supplier):
    inn = supplier.get('inn', '')
    if inn is None:
        inn = ''
    kpp = supplier.get('kpp', '')
    if kpp is None:
        inn = ''

    if len(inn) == 12 and (kpp == '' or kpp is None):
        return True
    elif len(inn) == 10 and len(kpp) == 9:
        return True
    else:
        return False


def error(text):
    """Показывает окно ошибки. Текст в окне прописывается в качестве аргумента к функции.
    В окне кнопка "Продолжить обработку" возвращает False, а "Пропустить документ" возвращает True"""

    error_window = ttkb.Toplevel(root)
    result = tk.BooleanVar()
    error_window.overrideredirect(True)  # Убирает рамку окна, включая верхнюю черную грань

    def on_continue():
        result.set(True)
        error_window.destroy()

    def repeat():
        result.set(False)
        error_window.destroy()

    def lift_above_all(event=None):
        error_window.lift()
        error_window.after(100, lift_above_all)  # Повторно вызывать каждые 100 мс

    # Вызовем lift_above_all сразу после создания окна
    lift_above_all()

    def on_error_window_close():
        result.set(False)
        error_window.destroy()
        return result.get()

    error_window.protocol("WM_DELETE_WINDOW", on_error_window_close)

    error_window.title("Ошибка данных")
    error_window.geometry(error_windows_size)
    error_window.config(bg='black')
    inner_frame = ttkb.Frame(error_window, borderwidth=0, relief="solid")
    inner_frame.pack(expand=True, fill='both', padx=1, pady=1)

    def start_move(event):
        error_window.x = event.x
        error_window.y = event.y

    def stop_move(event):
        error_window.x = None
        error_window.y = None

    def on_move(event):
        deltax = event.x - error_window.x
        deltay = event.y - error_window.y
        x = error_window.winfo_x() + deltax
        y = error_window.winfo_y() + deltay
        error_window.geometry(f"+{x}+{y}")

    # Привязка событий для перемещения окна
    inner_frame.bind("<ButtonPress-1>", start_move)
    inner_frame.bind("<ButtonRelease-1>", stop_move)
    inner_frame.bind("<B1-Motion>", on_move)

    # Добавление кнопки для закрытия окна
    close_button = ttkb.Button(inner_frame, text="X", command=repeat, bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top', anchor='ne', padx=5, pady=5)

    # Настройка шрифта
    custom_font = font.nametofont("TkDefaultFont")

    # Использование Text виджета для выделяемого текста с серым фоном
    error_text = tk.Text(inner_frame,
                         height=16,
                         width=46,
                         wrap='word',
                         fg="red",
                         font=custom_font,
                         relief=tk.FLAT,
                         bd=0)

    error_text.insert('1.0', text)
    error_text.tag_configure("center", justify='center')
    error_text.tag_add("center", "1.0", "end")
    error_text.config(state=tk.DISABLED)
    error_text.pack(pady=0)

    # Создание фрейма для кнопок
    button_frame = ttkb.Frame(inner_frame)
    button_frame.pack(pady=10)

    repeat_button = ttkb.Button(button_frame, text="Продолжить обработку", command=repeat, bootstyle=(SUCCESS, OUTLINE))
    repeat_button.pack(side=tk.LEFT, padx=10)

    continue_button = ttkb.Button(button_frame, text="Пропустить документ", command=on_continue,
                                  bootstyle=(DANGER, OUTLINE))
    continue_button.pack(side=tk.LEFT, padx=10)

    logging.warning(f'Уведомление об ошибке: {text}')

    show_notification(text)

    error_window.wait_variable(result)

    return result.get()


def on_submit_sbis(login, password, window):
    if login:
        try:
            sbis.auth(login, password)
            status_label.config(text=f'✔ Подключено: {login}', foreground="green")

        except Exception:
            status_label.config(text=f'(!) Ошибка: {login}', foreground="red")

        password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
        save_data({login: password_hash_string}, SBIS_CONN_PATH)

    window.destroy()


def update_iiko_status(login, new_status):
    for line in tree.get_children():
        if tree.item(line, 'values')[0] == login:
            tree.item(line, values=(login, new_status))
            break


def update_sbis_status(login, status, color):
    update_queue.put(lambda: status_label.config(text=f'{status}: {login}', foreground=f'{color}'))


def doc_print(json_doc):
    log(json.dumps(json_doc, indent=4, sort_keys=True, ensure_ascii=False))


def get_digits(string):
    return re.sub('\D', '', string)


def create_responsible_dict(store_name):
    if store_name:
        words = store_name.split()
        return {
            'Фамилия': words[0],
            'Имя': words[1] if len(words) > 1 else '',
            'Отчество': ' '.join(words[2:]) if len(words) > 2 else ''
        }

    return {}


class NoAuth(Exception):
    pass


class SABYAccessDenied(Exception):
    pass


class IIKOManager:
    def __init__(self, iiko_connect_list):
        self.connect_list = iiko_connect_list
        self.server_address = iiko_server_address
        self.cryptokey = CRYPTOKEY
        self.login = None
        self.include_v2 = False

    def get_auth(self, password):
        login = self.login
        password_hash = (hashlib.sha1(password.encode())).hexdigest()
        url = f'https://{iiko_server_address}:443/resto/api/auth?login={login}&pass={password_hash}'
        res = requests.get(url)

        log(f'Method: get_auth() | Code: {res.status_code} \n')
        logging.debug(f'URL: {url} \n'
                      f'Result: {res.text}')

        match res.status_code:

            case 200:
                log(f'Авторизация в IIKO прошла. {login}: вход выполнен.')
                with open(f"{login}_iiko_token.txt", "w+") as file:
                    iiko_key = res.text
                    file.write(str(iiko_key))
                    return iiko_key

            case 401:
                update_queue.put(lambda: update_iiko_status(login, 'Неверный логин/пароль'))
                raise NoAuth('Неверный логин/пароль. \n'
                             'Пароль можно изменить в IIKO Office:\n'
                             '-- [Администрирование]\n'
                             '-- [Права доступа]\n'
                             '-- Правой кнопкой мыши по пользователю\n'
                             '-- [Редактировать пользователя]\n'
                             '-- Поле "Пароль"\n'
                             '-- [Сохранить]')

            case _, *code:
                update_queue.put(lambda: update_iiko_status(login, f'(!) Ошибка. Код: {code}'))

                raise NoAuth(f'Код {code}, не удалось авторизоваться в IIKO. Ответ сервера: {res.text}')

    def get_key(self):
        login = self.login
        iiko_hash = self.connect_list[f'{login}']
        password = self.cryptokey.decrypt(iiko_hash).decode()

        try:
            with open(f"{login}_iiko_token.txt", "r") as file:
                iiko_key = file.read()
                return {'login': login, 'password': password, 'key': iiko_key}

        except FileNotFoundError:
            log(f'Аккаунт IIKO - {login}: авторизуемся...')
            iiko_key = self.get_auth(password)
            return {'login': login, 'password': password, 'key': iiko_key}

    def get_query(self, method, params=None):
        if params is None:
            params = {}

        base_url = f'https://{self.server_address}:443/resto/api/'

        if self.include_v2:
            base_url += 'v2/'
            self.include_v2 = False

        url = base_url + method
        iiko_account = self.get_key()
        params['key'] = iiko_account.get('key')

        res = requests.get(url, params)

        log(f'Method: GET {method} | Code: {res.status_code}')
        logging.debug(f'URL: {url} \n'
                      f'Parameters: {params} \n'
                      f'Result: {res.text}')

        match res.status_code:

            case 200:
                update_queue.put(lambda: update_iiko_status(iiko_account.get('login'), f'✔ Подключено'))
                return res.text

            case 401:
                params['key'] = self.get_auth(iiko_account.get('password'))
                res = requests.get(url, params)
                return res.text

            case _, *code:
                logging.warning(f'Code: {code}, Method: GET {method}, response: {res.text}')
                update_queue.put(lambda: update_iiko_status(key.get('login'), f'(!) Ошибка. Код: {code}'))

                text = f"Ошибка в подключении к IIKO. Код ошибки {code}. Обратитесь к системному администратору.",
                show_notification(text)

                return f'Error {code}. See warning logs.'

    def search_income_docs(self, from_date: str):
        params = {'from': from_date,
                  'to': date.today().strftime('%Y-%m-%d')}

        return self.get_query(f'documents/export/incomingInvoice', params)

    def supplier_search_by_id(self, supplier_id: str = ''):
        """Возвращает данные поставщика по его id.
        Id поставщика можно найти в поле документа-поступления ['supplierId'] из метода search_income_docs()
        Документация: https://ru.iiko.help/articles/#!api-documentations/suppliers"""

        suppliers_list = xmltodict.parse(self.get_query('suppliers'))

        for supplier in suppliers_list['employees']['employee']:

            if not supplier['id'] == supplier_id:
                continue

            res = {'name': (supplier.get('name')).replace('"', ''),
                   'inn': supplier.get('taxpayerIdNumber', ''),
                   'address': supplier.get('address', '-'),
                   'cardNumber': supplier.get('cardNumber', ''),
                   'email': supplier.get('email', '@'),
                   'phone': supplier.get('phone', '-'),
                   'note': supplier.get('note')}

            note = res.get('note')
            if note:
                kpp_pattern = r"КПП:(\d{9})"
                match = re.search(kpp_pattern, note.replace(' ', ''))
                if match:
                    res['kpp'] = match.group(1)

            return res

    def get_org_info_by_store_id(self, store_id):

        store_dict = xmltodict.parse(self.get_query('corporation/stores'))
        orgs_dict = xmltodict.parse(self.get_query(f'corporation/departments'))

        for store in store_dict.get("corporateItemDtoes", {}).get("corporateItemDto", []):

            if store.get("id") == store_id:
                parent_id = store.get("parentId")
                store_name = store.get("name")
                orgs_dict = orgs_dict.get("corporateItemDtoes", {}).get("corporateItemDto", [])

                while True:
                    for organisation in orgs_dict:

                        if organisation.get("id") == parent_id:
                            if organisation.get("type") == "DEPARTMENT":
                                parent_id = organisation.get("parentId")

                            elif organisation.get("type") == "JURPERSON":
                                jur_info = organisation.get("jurPersonAdditionalPropertiesDto", {})

                                return {'store_name': store_name,
                                        'inn': jur_info.get("taxpayerId"),
                                        'kpp': jur_info.get("accountingReasonCode")}

        return {}

    def get_concepts(self):

        params = {'rootType': 'Conception',
                  'includeDeleted': False}

        self.include_v2 = True
        conceptions_list = json.loads(self.get_query('entities/list', params))
        conceptions_dict = {}

        for concept in conceptions_list:
            conceptions_dict[f'{concept.get("id")}'] = concept.get("name")

        return None if conceptions_dict == {} else conceptions_dict


class SBISManager:
    def __init__(self, sbis_connection_list):
        self.cryptokey = CRYPTOKEY
        self.regulations_id = sbis_regulations_id
        self.connection_list = sbis_connection_list
        self.base_url = 'https://online.sbis.ru'
        self.headers = {'Host': 'online.sbis.ru',
                        'Content-Type': 'application/json-rpc; charset=utf-8',
                        'Accept': 'application/json-rpc'}
        self.login = None

    def auth(self, login, password):
        self.login = login
        payload = {"jsonrpc": "2.0",
                   "method": 'СБИС.Аутентифицировать',
                   "params": {"Логин": login, "Пароль": password},
                   "protocol": 2,
                   "id": 0}

        res = requests.post(f'{self.base_url}/auth/service/', headers=self.headers, data=json.dumps(payload))
        sid = json.loads(res.text)['result']

        with open(f"{login}_sbis_token.txt", "w+") as file:
            file.write(str(sid))

        return sid

    def get_sid(self):
        login = self.login
        password_hash = self.connection_list[login]
        password = self.cryptokey.decrypt(password_hash).decode()

        try:
            with open(f"{login}_sbis_token.txt", "r") as file:
                sid = file.read()
                return {'login': login,
                        'password': password,
                        'sid': sid}

        except FileNotFoundError:

            try:
                sid = self.auth(login, password)
                return {'login': login,
                        'password': password,
                        'sid': sid}

            except Exception:
                logging.critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                update_sbis_status(login, '(!) Ошибка', "red")

    def main_query(self, method: str, params: dict or str):
        sid = self.get_sid()
        self.headers['X-SBISSessionID'] = sid['sid']
        payload = {"jsonrpc": "2.0",
                   "method": method,
                   "params": params,
                   "protocol": 2,
                   "id": 0}

        res = requests.post('https://online.sbis.ru/service/', headers=self.headers,
                            data=json.dumps(payload))

        log(f'Method: {method} | Code: {res.status_code}')
        logging.debug(f'URL: https://online.sbis.ru/service/ \n'
                      f'Headers: {self.headers}\n'
                      f'Parameters: {params}\n'
                      f'Result: {json.loads(res.text)}')

        match res.status_code:

            case 200:
                update_sbis_status(sid['login'], '✔ Подключено', 'green')
                return json.loads(res.text)['result']

            case 401:
                log('Требуется обновление токена.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(sid['login'], sid['password'])
                res = requests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']

            case 500:
                status_label.config(text=f'! Ошибка ! {sid["login"]}')

                text = f"Ошибка в подключении к СБИС. Сервер недоступен. Код 500",
                show_notification(text)

                raise AttributeError(f'{method}: Check debug logs.')

    def search_doc(self, num, doc_type, doc_date):

        assert any(map(str.isdigit, num)), 'СБИС не сможет найти документ по номеру, в котором нет цифр'

        params = {"Фильтр": {"Маска": num,
                             "ДатаС": doc_date,  # '17.01.2024'
                             "ДатаПо": doc_date,  # '17.01.2024'
                             "Тип": doc_type}}
        res = self.main_query("СБИС.СписокДокументов", params)

        return None if len(res['Документ']) == 0 else res['Документ'][0]

    def search_agr(self, inn):
        if inn is not None:
            assert any(map(str.isdigit, inn)), 'СБИС не сможет найти договор по номеру, в котором нет цифр'

            params = {"Фильтр": {"Маска": inn,
                                 "ДатаС": '01.01.2020',
                                 "ДатаПо": date.today().strftime('%d.%m.%Y'),
                                 "Тип": "ДоговорИсх"}}
            res = self.main_query("СБИС.СписокДокументов", params)

            return None if len(res['Документ']) == 0 else res['Документ'][0]
        return None

    def agreement_connect(self, agr_id: str, doc_id: str):

        params = {
            "Документ": {
                'ВидСвязи': 'Договор',
                "Идентификатор": agr_id,
                "ДокументСледствие": {
                    "Документ": {
                        'ВидСвязи': 'Договор',
                        "Идентификатор": doc_id}}}}

        self.main_query("СБИС.ЗаписатьДокумент", params)

    def get_today_docs(self, income_date, doc_type):

        params = {"Фильтр": {"ДатаС": income_date,
                             "ДатаПо": income_date,
                             "Тип": doc_type,
                             "Навигация": {"РазмерСтраницы": '200'}}}

        res = self.main_query("СБИС.СписокДокументов", params)
        return None if len(res['Документ']) == 0 else res['Документ']


root = ttkb.Window(themename="journal", title=main_title)
root.geometry(main_windows_size)
root.protocol("WM_DELETE_WINDOW", on_root_close)

iiko_connect = load_data(IIKO_CONN_PATH)
sbis_connect = load_data(SBIS_CONN_PATH)
iiko = IIKOManager(iiko_connect)
sbis = SBISManager(sbis_connect)
sbis_Perezagruzka = sbis
sbis_PlanetaM = SBISManager({"\u041f\u043b\u0430\u043d\u0435\u0442\u0430\u041c": "gAAAAABm4axW8TsxHcLedsJbfrb6MQshdYKORnNz5hMM26LthUIGFySKGZFXPdrHn6_qlARAFhruvT7sKX7VIhkK3DlNQhly4w=="})
sbis_Andreev = SBISManager({"\u0410\u043d\u0434\u0440\u0435\u0435\u0432\u0418\u0412": "gAAAAABm4a8YZfn6V7y3yz1cuLjIYBTJbQTMHYHKC74Z4E9BUXWrmcEFKrurXdoFs6ipw4N28xvKCNMY4i50UHxSCiUnBQnjmw=="})

icon_data = base64.b64decode(encoded)
iiko_icon = Image.open(BytesIO(icon_data))
with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name
root.iconbitmap(default=temp_icon_path)
app_icon = ImageTk.PhotoImage(iiko_icon)
root.call('wm', 'iconphoto', root._w, app_icon)
os.remove(temp_icon_path)

tree = ttk.Treeview(root, columns=("login", "status"), show='headings')

tree.heading('login', text="Логин")
tree.heading('status', text="Статус")
tree.column("login", width=90, anchor='center')
tree.column("status", width=150, anchor='center')
tree.pack(pady=5)

for key in iiko_connect.keys():
    tree.insert('', 'end', values=(key,))

ttk.Button(root, text="Добавить соединение", command=lambda: create_connection_window("")).pack(pady=20)
ttk.Button(root, text="Удалить соединение", command=remove_connection).pack(pady=5)

separator = ttkb.Separator(root, orient='horizontal')
separator.pack(fill='x', padx=5, pady=20)

sbis_button = ttk.Button(root, text="Соединение СБИС", command=lambda: create_connection_window("СБИС", True),
                         bootstyle=INFO)
sbis_button.pack(side=tk.TOP, padx=10, pady=10)

status_label = ttkb.Label(root, text="Не подключено")
status_label.pack(side=tk.TOP, padx=10, pady=0)


# ЕСЛИ ВНЕСЕНА НОВАЯ ОРГАНИЗАЦИЯ, НАДО В ТОЧНОСТИ ДО ПРОБЕЛОВ ВНЕСТИ СЮДА ИМЯ КОНЦЕПЦИИ
def get_inn_by_concept(concept_name):
    inn_mapping = {'Мелконова А.А.': '010507778771',
                   'Мелконова Анастасия': '010507778771',
                   'Каблахова Д.А.': '090702462444',
                   'Мелконов Г.С.': '231216827801',
                   'ИП МЕЛКОНОВ': '231216827801',
                   'ИП Журавлев С.С.': '232910490605',
                   'Богданов М.А.': '010102511000',
                   'ИП Андреев И.В.': '592007906504'}

    return inn_mapping.get(concept_name)


async def job(iiko_connect_list, sbis_connection_list):
    logging.warning(f"Запуск цикла. Цикл запускается каждые {SECONDS_OF_WAITING} секунд.")
    doc_count = 0
    while not stop_event.is_set():
        try:
            assert len(sbis_connection_list) > 0, 'Отсутствует аккаунт СБИС'

            for sbis_login in sbis_connection_list.keys():
                sbis.login = sbis_login

            assert len(iiko_connect_list) > 0, 'Отсутствуют IIKO подключения'

            for iiko_login in iiko_connect_list.keys():
                log(f'Соединение с аккаунтом IIKO: {iiko_login}')
                iiko.login = iiko_login

                try:
                    concepts = iiko.get_concepts()
                    search_date = datetime.now() - timedelta(days=search_doc_days)
                    income_iiko_docs = xmltodict.parse(iiko.search_income_docs(search_date.strftime('%Y-%m-%d')))
                    assert income_iiko_docs['incomingInvoiceDtoes'] is not None, 'В IIKO нет приходных накладных'

                    invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                    if type(invoice_docs) == dict:
                        invoice_docs = [invoice_docs]

                    for iiko_doc in reversed(invoice_docs):
                        assert stop_event.is_set() is False, 'Программа завершила работу'

                        try:
                            iiko_doc_num = iiko_doc.get("documentNumber").replace(' ', '')
                            logging.warning(f'№{iiko_doc_num} от {iiko_doc.get("incomingDate")} обрабатывается...')

                            if iiko_doc.get('status') != 'PROCESSED':
                                logging.warning(f'Неактуален в IIKO. Пропуск... \n')
                                continue

                            concept_id = iiko_doc.get('conception')
                            log(f"""{concept_id = }""")
                            if concept_id is None or concept_id == '2609b25f-2180-bf98-5c1c-967664eea837':
                                logging.warning(f'Без концепции в IIKO. Пропуск... \n')
                                continue

                            else:
                                concept_name = concepts.get(f'{concept_id}')
                                log(f"""{concept_name = }""")

                                if concept_name in CONCEPT_IGNORE_LIST:
                                    logging.warning(f'Концепция в чёрном списке. Пропуск... \n')
                                    continue

                                if 'ооо' in concept_name.lower():
                                    is_sole_trader = False
                                else:
                                    is_sole_trader = True

                            supplier = iiko.supplier_search_by_id(iiko_doc.get("supplier"))
                            log(supplier)

                            if supplier.get('name') is None or supplier.get('name').lower() == 'рынок':
                                logging.warning(f'Мягкий чек в IIKO. Пропуск...\n')
                                continue

                            if stop_event.is_set():
                                break

                            while not validate_supplier(iiko.supplier_search_by_id(iiko_doc.get("supplier"))):

                                if stop_event.is_set():
                                    break
                                message = (f"Некорректные данные поставщика в IIKO:\n"
                                           f"{supplier.get('name')}\n"
                                           f"ИНН: {supplier.get('inn', 'Не заполнено')}\n"
                                           f"Доп. сведения: {supplier.get('note', '')}\n\n"
                                           f"Корректно пропишите ИНН для физ. лиц\n"
                                           f"Для юр. лиц впишите КПП в карточке поставщика во вкладке \"Дополнительные сведения\" в белом прямоугольнике для текста\n"
                                           f"в формате \"КПП: 123456789\".\n\n"
                                           f"Исправьте данные, подождите полминуты, и нажмите\n"
                                           f"[ Продолжить обработку ]\n")
                                error_result = error(message)

                                if stop_event.is_set():
                                    break

                                if error_result:
                                    break

                            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')

                            sbis_doc = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)

                            if sbis_doc:
                                logging.warning(f'Документ уже обработан в СБИС. Пропуск... \n')
                                continue

                            with open(XML_FILEPATH, 'w') as file:
                                file.write(f'''<?xml version="1.0" encoding="WINDOWS-1251" ?>
    <Файл ВерсФорм="5.02">

    <СвУчДокОбор>
    <СвОЭДОтпр/>
    </СвУчДокОбор>

    <Документ ВремИнфПр="9.00.00" ДатаИнфПр="{income_date}" КНД="1175010" НаимЭконСубСост="{supplier.get('name')}">
    <СвДокПТПрКроме>
    <СвДокПТПр>
    <НаимДок НаимДокОпр="Товарная накладная" ПоФактХЖ="Документ о передаче товара при торговых операциях"/>
    <ИдентДок ДатаДокПТ="{income_date}" НомДокПТ="{iiko_doc_num}"/>
    <СодФХЖ1>
      <ГрузПолуч ОКПО="06525502">
        <ИдСв>
          <СвОрг>
            <СвЮЛ ИННЮЛ="2311230064" КПП="231001001" НаимОрг="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ &quot;ЛЕАР ГРУПП&quot;"/>
          </СвОрг>
        </ИдСв>
        <Адрес>
          <АдрИнф АдрТекст="г. Краснодар, ул. им. 40-летия Победы, д. 20, Строение 1, ПОМЕЩЕНИЕ 308, 350042" КодСтр="643"/>
        </Адрес>
        <Контакт Тлф="8 (861) 204-05-06" ЭлПочта="dir@le-ar.ru"/>
        <БанкРекв НомерСчета="40702810512550035771">
          <СвБанк БИК="044525360" КорСчет="30101810445250000360" НаимБанк="Филиал &quot;Корпоративный&quot; ПАО &quot;Совкомбанк&quot; МОСКВА"/>
        </БанкРекв>
      </ГрузПолуч>
      <Продавец>
        <ИдСв>
          <СвОрг>
            <СвЮЛ ИННЮЛ="{supplier.get('inn')}" ''')

                                if supplier.get('kpp'):
                                    file.write(f'''КПП="{supplier['kpp']}" ''')

                                file.write(f'''НаимОрг="{supplier.get('name')}"/>
          </СвОрг>
        </ИдСв>
        <Адрес>
          <АдрИнф АдрТекст="{supplier.get('address')}" КодСтр="643"/>
        </Адрес>
        <Контакт Тлф="{supplier.get('phone')}" ЭлПочта="{supplier.get('email')}"/>
        <БанкРекв НомерСчета="{supplier.get('cardNumber')}">
          <СвБанк/>
        </БанкРекв>
      </Продавец>
      <Покупатель ОКПО="06525502">
        <ИдСв>
          <СвОрг>
            <СвЮЛ ИННЮЛ="2311230064" КПП="231001001" НаимОрг="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ &quot;ЛЕАР ГРУПП&quot;"/>
          </СвОрг>
        </ИдСв>
        <Адрес>
          <АдрИнф АдрТекст="350042, г. Краснодар, ул. им. 40-летия Победы, д. 20, Строение 1, ПОМЕЩЕНИЕ 308" КодСтр="643"/>
        </Адрес>
        <Контакт Тлф="8 (861) 204-05-06" ЭлПочта="dir@le-ar.ru"/>
        <БанкРекв НомерСчета="40702810512550035771">
          <СвБанк БИК="044525360" КорСчет="30101810445250000360" НаимБанк="Филиал &quot;Корпоративный&quot; ПАО &quot;Совкомбанк&quot; МОСКВА"/>
        </БанкРекв>
      </Покупатель>
      <Основание НаимОсн="Договор" НомОсн="{supplier.get('inn')}"/>
      <ИнфПолФХЖ1>
        <ТекстИнф Значен="{supplier.get('inn')}" Идентиф="ДоговорНомер"/>
      </ИнфПолФХЖ1>
    </СодФХЖ1>
    </СвДокПТПр>      
    <СодФХЖ2>''')
                                item_num = 1
                                total_price = 0
                                total_without_vat = 0
                                total_amount = 0
                                items = iiko_doc['items']['item']

                                if type(items) is dict:
                                    items = [items]
                                for item in items:
                                    code = item.get("productArticle")
                                    sum = float(item.get('sum', '0'))
                                    price = float(item.get('price', sum))
                                    vat_percent = float(item.get("vatPercent", '0'))
                                    actual_amount = float(item.get('actualAmount', '1'))
                                    price_without_vat = float(item.get('priceWithoutVat', price))

                                    total_price += sum
                                    total_amount += actual_amount
                                    total_without_vat += sum - (sum * vat_percent)

                                    file.write(f'''
                                <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{price_without_vat * actual_amount}" СтУчНДС="{sum}" Цена="{price}">
                                  <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПоставщика"/>
                                  <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПокупателя"/>
                                  <ИнфПолФХЖ2 Значен="&quot;Type&quot;:&quot;Товар&quot;" Идентиф="ПоляНоменклатуры"/>
                                  <ИнфПолФХЖ2 Значен="41-01" Идентиф="СчетУчета"/>
                                </СвТов>''')
                                    item_num += 1
                                file.write(f'''
                                <Всего НеттоВс="{total_amount}" СтБезНДСВс="{total_without_vat}" СтУчНДСВс="{total_price}"/>
                              </СодФХЖ2>
                            </СвДокПТПрКроме>
                            <СодФХЖ3 СодОпер="Перечисленные в документе ценности переданы"/>
                            </Документ>

                            </Файл>''')

                            # Ищет документ в СБИС с такой же суммой и той же датой
                            is_copy = False
                            today_docs = sbis.get_today_docs(income_date, 'ДокОтгрВх')
                            for sbis_doc in today_docs:

                                sbis_sum = sbis_doc.get('Сумма', '0')

                                if sbis_sum == total_price:
                                    sbis_name = sbis_doc.get('Контрагент', '').get('СвЮЛ' or "СвФЛ", '').get(
                                        'НазваниеПолное', 'Неизвестный')

                                    passed = error(f'''Обнаружен похожий документ:
                                          В IIKO: {income_date} / От {supplier.get('name')} на сумму {total_price}\n
                                          В СБИС: {income_date} / От {sbis_name} на сумму {sbis_sum}''')

                                    if passed:
                                        is_copy = True
                                        break

                            # Пропускает документ, если пользователь нажал "Пропустить документ"
                            if is_copy:
                                continue

                            with open(XML_FILEPATH, "rb") as file:
                                encoded_string = base64.b64encode(file.read())
                                base64_file = encoded_string.decode('ascii')

                            org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                            # TODO: Ответсвенный снесён. Склад не учитывается. Крепится ближайший
                            # responsible = create_responsible_dict(org_info.get('store_name'))

                            org_inn = get_inn_by_concept(concept_name)
                            if is_sole_trader and org_inn is not None:
                                organisation = {"СвФЛ": {"ИНН": org_inn}}
                            else:
                                organisation = {"СвЮЛ": {"ИНН": org_info.get('inn'),
                                                         "КПП": org_info.get('kpp')}}

                                if organisation["СвЮЛ"]["ИНН"] in INN_IGNORE_LIST:
                                    log('Это внутреннее перемещение.')
                                    continue

                            params = {"Документ": {"Тип": "ДокОтгрВх",
                                                   "Регламент": {"Идентификатор": sbis.regulations_id},
                                                   'Номер': iiko_doc_num,
                                                   "Примечание": supplier.get('name'),
                                                   # TODO: Ответсвенный снесён. Склад не учитывается. Крепится ближайший
                                                   # "Ответственный": responsible,
                                                   "НашаОрганизация": organisation,
                                                   "Вложение": [
                                                       {'Файл': {'Имя': XML_FILEPATH, 'ДвоичныеДанные': base64_file}}]
                                                   }}

                            agreement = sbis.search_agr(supplier['inn'])
                            error_message = (f'Ошибка в номенклатуре.\n'
                                             f'Добавьте в СБИС позиции из IIKO:\n\n'
                                             f'[ Бизнес ]\n'
                                             f'[ Каталог ]\n'
                                             f'[ + ]\n'
                                             f'[ Загрузить    > ]\n'
                                             f'[ Выгрузка номенклатуры из IIKO ]\n\n\n'
                                             f'В СБИС справа внизу появится таймер, показывающий прогресс переноса позиций.\n'
                                             f'Подождите, пока всё не синхронизируется, и нажмите\n[ Продолжить обработку ]')
                            #error_message = (f'Ошибка. Зафиксировано в логах. Свяжитесь с администратором.')

                            if agreement is None or agreement == 'None':
                                try:
                                    new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)

                                    log(f"Договор с ИНН №{supplier['inn']} не найден в СБИС."
                                        f"Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")

                                except AttributeError:
                                    error(error_message)
                                    pass

                            else:
                                agreement_note = get_digits(agreement['Примечание'])

                                if agreement_note == '':
                                    agreement_note = '7'

                                payment_days = int(agreement_note)
                                deadline = datetime.strptime(income_date, '%d.%m.%Y') + timedelta(
                                    days=payment_days)
                                deadline_str = datetime.strftime(deadline, '%d.%m.%Y')

                                params['Документ']['Срок'] = deadline_str
                                params['Документ']['ВидСвязи'] = 'Договор'
                                params['Документ']['ДокументОснование'] = {
                                    "Документ": {
                                        'ВидСвязи': 'Договор',
                                        "Идентификатор": agreement["Идентификатор"]}}
                                try:
                                    new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                                    sbis.agreement_connect(agreement["Идентификатор"], new_sbis_doc["Идентификатор"])

                                    log(f"Договор №{supplier['inn']} прикреплён к документу №{new_sbis_doc['Номер']}.")
                                except AttributeError:
                                    error(error_message)
                                    pass

                            os.remove(XML_FILEPATH)

                            update_queue.put(lambda: update_iiko_status(iiko_login, '✔ Подключено'))

                            doc_count += 1
                            logging.warning(
                                f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

                        except Exception as e:
                            logging.warning(f'Ошибка при обработке документа: {e} | {traceback.format_exc()}')
                            break

                except NoAuth:
                    update_queue.put(lambda: update_iiko_status(iiko_login, 'Неверный логин/пароль'))

                except Exception as e:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(!) Ошибка'))
                    logging.warning(f'Цикл прервался. {e} | {traceback.format_exc()}')

                except ConnectionError:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(?) Подключение...'))

        except Exception as e:
            logging.warning(f'Ошибка: {e}\n\n {traceback.format_exc()}')

        finally:
            log(f"Завершение текущего цикла. Обработано документов: {doc_count}.\n\n")
            await asyncio.sleep(SECONDS_OF_WAITING)


update_queue = Queue()
root.update_idletasks()
process_queue()

new_loop = asyncio.new_event_loop()
root.after(400, process_queue)
stop_event = threading.Event()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
thread.start()

asyncio.run_coroutine_threadsafe(job(iiko_connect, sbis_connect), new_loop)

root.mainloop()
