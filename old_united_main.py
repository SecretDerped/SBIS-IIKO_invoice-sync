import re
import os
import sys
import time
import json
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
from PIL import Image
from io import BytesIO
from queue import Queue
from tkinter import ttk, font
from logging import info as log
from cryptography.fernet import Fernet
from datetime import datetime, timedelta, date
from pystray import Icon as TrayIcon, MenuItem

log_level = logging.DEBUG
search_doc_days = 14
SECONDS_OF_WAITING = 5

XML_FILEPATH = 'income_doc_cash.xml'
IIKO_CONN_PATH = 'iiko_cash.json'
SBIS_CONN_PATH = 'sbis_cash.json'

add_window_size = "210x120"
main_windows_size = "300x380"

iiko_server_address = 'city-kids-pro-fashion-co.iiko.it'
sbis_regulations_id = '129c1cc6-454c-4311-b774-f7591fcae4ff'
CRYPTOKEY = Fernet(b'fq1FY_bAbQro_m72xkYosZip2yzoezXNwRDHo-f-r5c=')

console_out = logging.StreamHandler()
file_log = logging.FileHandler(f"application.log", mode="w")
logging.basicConfig(format='[%(asctime)s | %(levelname)s]: %(message)s',
                    handlers=(file_log, console_out),
                    level=log_level)


def start_async_loop(loop, event):
    asyncio.set_event_loop(loop)

    while not event.is_set():
        loop.run_forever()

    loop.close()


def show_window():
    root.deiconify()


def hide_window():
    root.withdraw()


def exit_program(the_icon):
    root.title("Выход...")

    stop_event.set()
    root.withdraw()
    the_icon.stop()
    new_loop.call_soon_threadsafe(new_loop.stop)
    thread.join()

    root.quit()
    root.destroy()
    sys.exit()


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


def create_connection_window(title, is_sbis=False):
    add_window = tk.Toplevel(root)
    add_window.title(title)
    add_window.geometry(add_window_size)

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

    submit_button = tk.Button(add_window, text=submit_button_text, command=command_action)
    submit_button.pack()


def validate_supplier(supplier):
    inn = supplier.get('inn', '')
    kpp = supplier.get('kpp', '')

    if len(inn) == 12 and (kpp == '' or kpp is None):
        return True
    elif len(inn) == 10 and len(kpp) == 9:
        return True
    else:
        return False


def error(text):
    error_window = tk.Toplevel(root)
    result = tk.BooleanVar()

    def on_continue():
        result.set(True)
        error_window.destroy()

    def repeat():
        result.set(False)
        error_window.destroy()

    error_window.title("Ошибка данных")
    error_window.geometry("400x200")

    # Настройка шрифта
    custom_font = font.Font(family="Roboto", size=12)

    # Использование Text виджета для выделяемого текста с серым фоном
    error_text = tk.Text(error_window,
                         height=5,
                         width=40,
                         wrap='word',
                         fg="red",
                         font=custom_font,
                         bg="#f0f0f0")

    error_text.insert('1.0', text)
    error_text.tag_configure("center", justify='center')
    error_text.tag_add("center", "1.0", "end")
    error_text.config(state=tk.DISABLED)
    error_text.pack(pady=20)

    # Создание фрейма для кнопок
    button_frame = tk.Frame(error_window)
    button_frame.pack(pady=10)

    repeat_button = tk.Button(button_frame, text="Ещё раз", command=repeat)
    repeat_button.pack(side=tk.LEFT, padx=10)

    continue_button = tk.Button(button_frame, text="Пропустить", command=on_continue)
    continue_button.pack(side=tk.LEFT, padx=10)

    root.wait_window(error_window)
    return result.get()


def on_submit_sbis(login, password, window):
    if login:
        try:
            sbis.auth(login, password)
            status_label.config(text=f'✔ Подключено: {login}', fg="blue")

        except Exception:
            status_label.config(text=f'(!) Ошибка: {login}', fg="red")

        password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
        save_data({login: password_hash_string}, SBIS_CONN_PATH)

    window.destroy()


def update_iiko_status(login, new_status):
    for line in tree.get_children():
        if tree.item(line, 'values')[0] == login:
            tree.item(line, values=(login, new_status))
            break


def update_sbis_status(login, status, color):
    update_queue.put(lambda: status_label.config(text=f'{status}: {login}', fg=f'{color}'))


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
        # logging.debug(f'URL: {url} \n'
        #              f'Parameters: {params} \n'
        #              f'Result: {res.text}')

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

            if res.get('note'):
                kpp_pattern = r"КПП: (\d{9})"
                match = re.search(kpp_pattern, res['note'])
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
                update_sbis_status(sid['login'], '✔ Подключено', 'blue')
                return json.loads(res.text)['result']

            case 401:
                log('Требуется обновление токена.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(sid['login'], sid['password'])
                res = requests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']

            case 500:
                status_label.config(text=f'(!) Ошибка: {sid["login"]}', fg="red")
                raise AttributeError(f'{method}: Check debug logs.')

    def search_doc(self, num, doc_type, doc_date):

        assert any(map(str.isdigit, num)), 'СБИС не сможет найти документ по номеру, в котором нет цифр'

        params = {"Фильтр": {"Маска": num,
                             "ДатаС": doc_date,  # '17.01.2024'
                             "ДатаПо": doc_date,  # '17.01.2024'
                             "Тип": doc_type}}
        res = self.main_query("СБИС.СписокДокументов", params)

        if len(res['Документ']) == 0:
            return None
        else:
            return res['Документ']

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


root = tk.Tk()
root.title("Соединения IIKO")
root.geometry(main_windows_size)
root.protocol('WM_DELETE_WINDOW', hide_window)

iiko_connect = load_data(IIKO_CONN_PATH)
sbis_connect = load_data(SBIS_CONN_PATH)
iiko = IIKOManager(iiko_connect)
sbis = SBISManager(sbis_connect)

icon_data = base64.b64decode(
    'AAABAAEAbW0AAAEAIACcwAAAFgAAACgAAABtAAAA2gAAAAEAIAAAAAAApLkAAAAAAAAAAAAAAAAAAAAAAAAzNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zI0zv8yM8v/MjbJ/zMzzv80M83/MzTN/zM0zf8zNM3/MjPM/zEyzP83OM//NjfQ/zY3y/82Ns3/NTjK/zY4y/84Ocv/NjTH/zg1y/86MtT/PjHU/0Qt0f9OPd7/RT3m/ygqzf8AALz/EBvD/ygsw/8yL8D/Mim8/zQqu/84Lrz/PDW8/0I/vP9MS73/VVXF/25s4P+Oke//nKLx/6es+/+wtP//tbb//7Cr//+cm+b/rrPs/6Gi7P+0sv//uLr//8rO///R1v//2Nj//9XU///Qz///zM3//6mq//+WnPn/ipHu/3J62/9bXdD/PD7B/ysowf8XD73/AACy/wAAsf8IIr//EjjO/zgryP87L8r/Oi/R/zUw1f81Ltv/LzHd/ygy1/8mM9L/NTHJ/zc0yP80Ncz/NzXL/zQ1y/8zNMr/MTXL/zIyzf8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM3y/8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM3/NTPM/zQyzv80Ncn/NDTK/zM3y/81M8v/ODPK/zg3zP83M8//OjrK/zw4xv9AQsX/QDfd/y4ixv8sOKv/wsX//7Oz//8nIK//NSbb/zY32/80NtL/NDDU/y4q1P8wLNL/MS7P/ykkx/8kHsT/KSfF/yAjwP8gJL//HiK9/xYYvf8AALb/pKb///D2///Mzf//AAC1/w4Fu/8bGsL/HSC//yEdyP8fGcb/GRXC/x0bwv8bGcL/FxW+/yYjxv8sKsr/LSvO/ywpzP8mHtH/Gg7P/7q0///o5v//YWPC/wAg0/89Md//Pzne/zs22v86MtT/NDvH/zQ5xf8xNMb/MDbL/zszyv85Nsz/NjbK/zQ2yv82Nsr/NDXK/zI2y/8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zI0zf8yM87/MjbL/zI2zf8yNMr/NjXK/y44yf8yN8j/PC7b/zk5wf8mPMD/O0bZ/woAuv9+gtX/8fr///j6///9+f//2tH//yYcsf8vNM//LDXF/zMxy/88OM3/NDXG/ywxx/8zNs//NjfP/y061P8xOdP/OSrO/yki0/8AAL7/VVvN//D1////////9/b//4iO6/8AD8P/Iiry/zsu4P8vMc3/MDHS/zIy1v8yM9X/NDLT/zg21v81MdT/NjLT/z00x/8nPeH/AAC6/764///9+v///Pv///Xu//+Hdtz/AAC+/z45xP8+OM//KT/J/zQ6yP87N87/NzPO/zY1zv80Mcr/NDXH/zgzzf8yM8z/NDPM/zU3y/8yM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zM87/MzfL/zQyz/8tNM//LjfR/zks2P8+N8X/P0De/wAAsf9yeM7/9f////H6/v/8//r////3//P3//+9xfn/Lyq+/zcy0/80M8n/NC3R/zYy0v8xM9L/MDbQ/zM00f8yNNP/LTDY/z444v8nE7v/Z2XT/+Lw///4/////f3///v9///y9v//hYvt/wAAwv8rN9r/NDXF/zE1x/8zNM3/MzXL/zM2zf8zM8//LzHN/zIx0P8fLeT/AAC7/66x9P/5+P///v3//////v///P//9+3//2Zsy/8aALz/KzDT/zU6zP81Ms7/OzLQ/zQxzf8zMc7/MzTM/zMyyf82Nc7/NDTO/zI0zv8yM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPM/zMzzf8yM87/NDTK/zA4wP8wOsL/Tkbf/x0At/+UkuP/8fr///X9///8/v///v3///3//P/7//7/9fz//7e4//8uGcD/PjTU/zEyyv8xL8j/NDnF/zo2yP82OsL/PjTT/0M59f8JALP/nJrr//Hx///6////+f////n+///7//7///3///n1//+Tle7/AAC5/zo71P87PtP/MjPN/zIzzP8yNM3/MTHO/zs51/8gIcj/AACz/8XE///8////+v/+/////f/+/v///////////f/y8P//cnDc/xoOyP85L7j/ODDT/zkyzf8yMMv/MjDL/zUyzv81MM3/MzbQ/zU0zP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM83/MjPM/zU2z/8yNc//NzXQ/y8zyP81Nc//NULd/wAArf+gl+n/+fj//////v/9//7///3////9///8////+//+////+v/v9P//srL//zIlvP8tLsv/NDfJ/zkzx/85N8j/PznG/yYq5v8AALL/sbT///f5/////v///f3///n9///9///////9///9/////P////r//6up//8AALv/JijC/zIyyv82O8//NTfS/zY10f8pJtX/AAC8/83S///z+P///P/7//n//P/+//v///3////8//////3///////by//9zctf/ABm3/zkx1f84Nc//NTDO/y8vzP80M87/MjHM/zUyz/8xNcz/MjTN/zI0zv8yM87/MjPO/zI0zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM83/NTbM/zU2zv84NNH/MDjM/yw1zP8vOND/RDTu/w4Aq/+lpen//P7///////////z//////////////////f////z///////z/+//8/+/4//+wtPz/Kia0/y4pyf81Mcr/PTTW/ywq2v8NAKv/u7T///j7///8/f///vz///3+///6/v///v/////+///+///////////8///5+P//ra3//wAJtv8gJtj/QTfQ/zwx1/8kL8r/FBy6/9nX///7/v///v////z////7//3//f/8///9/////f////7////+/v////3/7+7//4R42/8ABbn/MiHP/zYxxf8jNs7/MzHL/zIxzf83M87/NjXP/zY0zf82M8v/NjbM/zc2zP81M8v/MjTO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MTLM/zg4z/8xM9D/MzbP/zcz0v8uNND/QT3g/xgAsv+sru7/+f7///7////+/v7//v/////////+/////v////7////9/////////////P/7//z/7PX//6aq9P80McH/JTbT/ycy1f8AAKb/xr3///vz///////////////9///+/////f////7//////////v////////////////////38//+govn/FhO6/yAbzP8qKMz/AAC3/97c///7+v7//////////////////v////7//v///v///////////////v/////1///////88f//dXra/x8Pwf8mNsb/KTHH/zUxzv80Mcz/NjTO/zUyz/81NM3/NTbJ/zU1yv82Nsr/NDPM/zI0zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPN/zU1zP84Ns7/MDjQ/zM7y/83L9P/SkHY/xYAov+8vf3/9f3///z////9/v///v////7////+/////v////7//////////v///////v////3//f/6//v////y+P//paz1/wAntv8AIK7/t7n7//78///9/fz//v7+//////////////////7////+/////////////////////////////v//////9/T//2pqx/8ADLT/AACl/97Z///+/f//////////////////////////////////////////////////////////9v////X//f37//P1//99fuP/AAC8/zExr/84NdT/NjDR/zY00P80Ms//NDTN/zU2yf81Nsr/NjbK/zQzzP8yNM7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTN/zUzzP80OM//LzTO/zg4zv8jNtX/NS7a/yMWov/Aw/j/9/7///39///////////////////+/////v////7////+//////////////////7////8//7/+/////z////9//T3//+3t+7/ysv6///+////+////////////////////////////////////v/////////////////////////+///////9///+///7+v//goTD/93f/////f/////////////////////////////////////////////////////9/////f////v////7/////P///f//8fL//29r3/8AGrH/ODTb/zY10/80Mdb/ODXN/zg1zv80NMv/NTTM/zYzy/80NMv/MjTO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTN/zQ0zf87M83/KzbP/yk8xP83M97/Ki3K/yUWrv/JzPv/9/r/////+////v///////////////////v////7////+/////v/////////////////+/////P////z////+/////v////////z////////++/////7////+/////////////////////////////////////////////////////////v////7///////7//Pr9//38/////////v7////////9/////////////////////////////////////////////f////3////+//////////////3///78///u7f//Wk7D/yglyP8gJND/LTrF/zk2w/80Ms3/NjPN/zUyzP82NdD/NDTM/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zI0zf8zNM7/PTLK/yo30f8lNtH/NSnU/zgssP/K0f7/+P/////8/////v////7////////////////////////+/////v////7//////////////////v////7////+///////////////////////////////////////////////////////////////////////////////////////////////////////+/////////////////////////////////////v/////////////////////////////////////////////////+///////////////////9/////v///P37//Pk//8lH7b/MTbU/yU2wv86NsT/NTDN/zIx0P82NM//NjLO/zQ1z/8yNMz/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM7/NDPM/zo1yP8mMsz/MyzY/0c9uv/T1v//8/////n7///+/f/////+///+//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7///////7+/v//////zNH//wUAr/8qMdT/OTXF/zUwzv8zMdD/NjTO/zYyzv80Nc//MjTM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTO/zIyzv80OcL/JzDB/0U91f/b4f//+//+//v5///9/v7//v7+/////v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////P///v/////+//D9/v+ms/v/Fxi5/zk6wP81Msr/MzHO/zY0z/82Ms//NDXM/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zNc7/MjrA/yoryP9hX+n/1Oj///3+/f/+/vv//f/9//z8///+///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+//////v///3////9///6//r/7/z//1lcx/8qLsD/MzHQ/zMwy/82M9D/NjLP/zQ1zP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzXN/zM4wv8yKeP/IR67/zdOwv/O1f//9fn9///+/f/7/P///f/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9///+//////////////7////V2P//AACm/zc22/8zMs7/NDXN/zU0zf80NM3/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM2y/8zNc3/MjPK/zg41P8vK9D/ACm1/7a3///+/f///fz///3////+//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7+/////v//9/z//3yB3v8hH7r/NDPO/zo1z/83Nsr/MzPO/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zNsv/MzXM/zM3yv8yMs3/NDHX/yQtx/8AAKv/s7r8//36///9/////f/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9///////+///////k6///Bwqt/y0pzv86O9D/NjfN/zYzyv81NM7/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzbL/zM2y/8zMs//MzXK/zE8vv9BM8L/LUHh/wAArv+1tf3/+fr///3+/////////v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////f/+/////f///P//9Pr//32C6P8mJrz/NTfQ/zc10P81M83/NTTN/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zM87/MzPO/zM3y/8zMtD/MDPQ/zUyzf82N9T/AAC9/7W38v/9/v/////////////+//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7//v////7////////////g6P//AACb/zg60P83MNL/NjXM/zE0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzTN/zM0zf80Nc//KivC/zc21v8AALD/vL7///77/////////v//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+P///1xZxf8vL8f/NTHO/zY1zP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zQ1z/8zM8n/Njvv/wAArP/Jzf//9vb///3////9/////f////3////+//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////T19f/e2///HBq6/zcx1/81Nc//MjTM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM83/MzfO/0E1xv8cJej/AACl/+bt///4/f//+//9//3//v/9////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+vn//zEpvP83L9n/NDXN/zI0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzv8wN8n/Ni/b/zIzyv8AHKr/6ff///X//P/+//7//f7///7+/////v////7////////////////+/////v//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9/r3///+//9SSsL/LifN/zU2zf8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzTN/zU9vf84QML/Hxy//z1Kuv/1+v////3///n9///8/v////7////+/////////////////v////7//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v//////j43w/yQewv8zM8//MjXN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzXL/zMv1f8zO77/MzvA/zgz3/8AAL3/lpfk///////3+P//+fn+//79/////v////////////////7//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v/9/////v////////////7+/v///v7//v79//3+/v/+///////////////////////////////////////////////////////////////+//n//v/+/7/D//8iF7//NjTT/zI1zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzXM/zMx0v8zMtD/MzLS/zM1zf80M8r/MzzP/wAAtP/g4f/////////////+/f/////////+/////v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v/+//r//f////7///////z//v/+/v3///3+////+v/7//3//f/////////////////////////////////////////////////////////////////7//3//v/X3///FwC6/zc11/8yNcz/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNcv/MzXP/zM0zP8zM87/NTLQ/yk7wv82M9n/EQCw/+vy///5/////v/8/////v///v////7////+///////////////////////////////////////////////////////////////////////////+//////////////////////////////////////////////////////////////////3//P/3//z//v78//38/v/4///////////+/v////r/+v7//////////////////////////////////////////////////////////////////////v/8////2N///xwSuv82M9n/MjXM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zP8zNM3/NDPN/zE2z/8uOMP/NTLR/zgqzv9XUcH/9fz///3/9v///////////////v///v////////////////////////////////////////////////////////78///z8f//ub/n//X9//////z////////////////////////////////////////////////////////////+////+v/8/////v/8/f//zNL6/+Hn//////////77//r5/////////////////////////////////////////////////////////////////////////P///9rc//8XDrb/NzbV/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf80M83/MTPP/zE3xf82K+T/Cgm+/8rC/v///////f////7/+/////3////////////////////////////////////////////////////////////9/f//x8L//wAAs/+0sP///fz///z+/v/8/v7//v7+//7+/v///////////////////////////////////////////////v////7/+f7//3163P8/Hs7/7/P////////9///////////////////////////////////////////////////////////////////////8//v////Gxf//FhGx/zU40f8yM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzXM/zQw1P8wOcL/MTPS/zE/5/8/H7D/9PD///z////9//z////9////////////////////////////////////////////////////////////+vz//7Kz//8kHtj/LyO9//Lq///8/v3//P7+//7+/v/+/v7//////////////////////////////////////////////v/////+//v///9xben/MSPa/4R26v/+/P//+////////////////////////////////////////////////////////////////////////f/9//7/pKD//yYjuv82N8//MjPO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zP8zNND/NDbI/zA2yP81L8v/ACHG/7W6///5/P///P/7/////f/////////////////////////////////+/////v////7////+/////v////n9//+Rk/D/Fg/Q/yohx/+zrf///v/+//z+/v/8/v///P7///3//f/+//7////////////////////////+/////v/////+//r//v/2+///Wl3b/yMj3P8iPeD/8O7///b9///+//z//v/8/////////////////////////v////7////+/////v////7////+////////+vz9/2Zizv8tJMP/NTTR/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTM/zMzzv80M87/NjTO/x0nyv9dYMj/9Pn///3//f////7//////////////////////////////////v////7////+/////v////7////1+v//YmbQ/xwbz/8rJ8r/e3ja///////+/////P3///z+///9//3//v/+/////////////////////////v////////7//P/3////9vj//0dF1v8uLdn/ACnL/8HC///6/////v/8//7//P////////////////////////7////+/////v////7////+/////v///v7+//H1//8yL7X/OTTX/zEyzP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zE1y/82Ltr/ISG3/+rv///+/////////////f////7///////////////////////7////+//7//v////7////+////6e///yYysf8qLtL/JSvO/0RJwv/79v////////z8///8/v///f/+//7//v///////////////////////////////v/+//v/9/7//+jm//8uJsz/NzTO/xopyv+IivP///7///7//P/+//z///////////////////////////////////7////+/////v////7////////J0P//ISa9/zQ10/80Nc3/NjPN/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8uNMn/RDTf/xkRx//e5P///f3////+//////3////+///////////////////////+/////v/+/////////////////87V//8SJbL/NDXT/x8s1P8oMrn/9u////v//f/7/P///f3///////////////////////////////////////////7//v/7//j9//+uqt3/GxrI/z44x/8pLcv/RknZ///9///+/v7//v7+///////////////////////////////////+//////7////////+/////v//X2nM/yYryf8qOc7/MTTK/zMzzv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPN/zQ2y/8kHsr/r6/6//v7///+//7////9//////////////////7////+/////v////////////////7///r3//+Jjef/ExzG/y0yxf8xL9H/ISW9/8LG///4+/n//P3////9///////////////+/////////////////v//////////////////+v//R0zS/xgnxv84NNH/MzHI/ykt0f/08P3//v7+//7+/v///v////////////////7////////////////////9/////v///f//4vD//xEAt/85MOL/KznN/zI2yf80M87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zQzz/8sOcX/KCLL/4WH0f/5+//////+/////f/////////////////+/////v////7//////v///////////v/j4P//Ixyy/y0z1f8vMMn/MTLS/yEnuv+sr/H//f////z//////f////7////+/////v////////////////7///////7////4/v//39z//xwA0P8nQ83/Ny3O/zcvyP8hIsj/6uj6//79///+/f////7////////////////+///////9//7//f/9///+//////v/+P/+/42R9v81Kdf/MDLG/y0w0f8yNc//MjTM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf80M8//LznH/yghyv99f8n/+fv///3//f/9//3//v////7////+/////v////7////+///////////////7+f//enba/ykkx/82OdL/NDXO/zMz0P8mKLv/qKzu///////+//////7////+/////v////7////////////////9/////f/+////8/f//z0zzf8tKM7/Ki7c/zUwyv8/Msn/ICHI/+ro+P/+/f///v3////+/////////////////v////3////9//n//v///P///f/6/9bm//8AAL7/LSbh/zk8wf89M9P/NzHP/zU1zP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTO/zEyyP8oJc7/lprf//b6///9//3//f/9//7////+/////f////3////+////////////+/////z/y8D+/xwArf8YLcL/ODfP/zU5yP80NNL/JCe9/7/D///6//7//P/////9/////v////7////+//////////////7//f////3//fz//5SL4f8AGMf/OiXd/zEyyP80Ns7/NzLN/ykpzf/18/////3////9/////v/////////////////////////////2+/////3+//z//v9tdtz/HybL/yo4x/85Ocr/QjTL/zU0yv8xNM7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zQ1zv8tL8f/IyDQ/87S///7/////f/9//3//f/+//7//v////z//v/8//z//v/9//7////9////4Of//zs6zv8sJ97/NzvG/zUt3/82KOP/LDTM/zUttv/57v//9/r///z5///+/f///f////7////////////////+///6//7/+////97Z//8ACsj/LTDE/zU3x/80OMf/KjDS/yosz/8zP9z///7////9/////f////7////+/////v///////////////////Pr///78//+7uP//AAC3/y0y1f81OMX/NjbM/zs4y/80M8v/MjTO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM7/NDXa/xEIrf/z8///+/7///3//v/9//3//v/+/////v////v////+//3//f/7//z/7/P//2lk2P8cGL7/MzfT/zc2y/8zN8v/MTnJ/ycp0P9QSsz/+/r///r//P/6/f///P7+//3////+///////////////8/////fv///D2//80Krn/HybG/zA1yv83MMn/MzbJ/ysz2f8oKM7/c3bp///+/v///f7///3+///////////////////////////////////////g6f//HRfA/zUzwv83N8n/MTLQ/zY00P80OND/MzPN/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/NDTM/zIzzv8yM83/NDPO/x0oyv9RTK//+/j////+///+//7//f/9//7//v////7////6///9///8/v//8/n//5eT8/8YAMP/NDfj/zM5xf87OMn/OjnD/zo3yP8fHL//kpTu//v+///7//v//v////7//v/9/////v/////////9////9fz///T4//9lYtD/ISLQ/zM0x/8wMcf/MTbM/zM5y/86N97/FhW//7+8+//9//7//P/8//z//P/9//3//f/9//3//f/9//3//f/9//3//f/p9v//REbM/x0sw/8zMsr/NTbP/zIzzf82Nc//NjjP/zQzzP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/NDTM/zAy0P83Nsj/MDTM/zs20v8AGcf/1s3////8/////v///v////3//f/+//7////+/////P//+////v7//8TA//8sFMD/HCLQ/yk7yP8xNs3/PDjE/zcyz/9BMOP/Gx+0/9jm///8/v7//P3///3////9/v///f7///7+//////////////f5//+Xoe//AADD/xcnu/83OMn/NjPK/zU2yf8zMsn/MSvb/zw32P/27v//+v/8//z//P/8//3//f/9//3//f/7//3/+//9//v//f/0+vb/XG/a/xgVs/86Pr3/ADzD/y8zzf8yMsz/NjTP/zY4z/80M8z/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTM/zUyz/8nOdL/OTPM/0E5yv8SOOP/Nx2h//75///+//7///7///7////9//3//v/+//7+/////////////9fS//8QFbL/HTbL/zQ7y/8rNcf/NTrH/zY4yf80Ns//KCfD/3Zy1f/8+P///P3///z9///8/v///P7///v8///8/v///v////z///+8wv//CwC8/yM0xv8nOtT/Nivd/zs2yf82NsX/NjXO/x0bt/+opez//v3///z//v////7////+/////f////3/9v/7//7//f/4+///lJDn/xMTvv8zNtX/NTLP/zYyz/82N9D/NzfP/zU3zv82N8//NDPM/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM3/MjTN/zIzzf8vNsz/LjXM/z021f9ALdz/Dg7B/8/M/////////f/+//3//v/9//3//f/+//7//v/+//r/+Pr6/9/c//80Lr3/MCjO/zk2z/8zOMb/NTnJ/zc6yP80NM7/LCvZ/zAwtP/r6P////////z9///8/v///f////z////5//3/9/7///n+///V2P//GwCu/zkn2P8uPcL/KjDb/zQ+vv89Nsv/OS/S/zQvzf9COLz/9Pr////9///8/////////////////v////3////9///4/v3/paD4/wAAqf80M9X/MDDN/zc40P82N8//NjbO/zU2zv81Ns7/NjfP/zQzzP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM3/NzPO/zU0y/82M87/NTDP/zQ+vv8xLt//OTLN/1pRwf/0+////P/8//3//f/9//3//P/9//z//P/8//z//////+fn//9JRcv/GRvL/ywq1/82M83/NjzJ/zY4yf8uNsb/OzrV/xwftP+gpOf//f7///z////9/////f////7////7/v//9/3+//P+///g6f//FACo/yoR0/83MtL/Mz7B/zU10P85P7T/PDHQ/0dB3f8AAKT/zsr///3/+f///f//+v///////////////v3///79///6/f//op/3/wAAwf8kOtX/MjXO/zc3z/81Ns7/NTbO/zU2zv81Ns7/NTbO/zY3z/80M8z/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/MjPM/zIzzP8yM8z/MjPM/zIzzP8xM8z/LzLO/zc4x/85M9b/NDPH/zY01f8/P7z/LDPn/wAApf/v9P//9/3///v8///+//r///////37///8//v/+/3///Lk//9VTNT/FhLG/zc3wf8yO8f/KjvP/zY6yv81Ocj/NTTO/xYmxf9HU7r/9vr///z////+/////v7///7////+/////v////n////l6///AACd/zEo0/83OMr/NTfR/zs2yP85PL3/PDTM/zwq4/8rKLr/dYPY//3///////7///7///z////9//7//v/9//z/+//8//v/qKv4/wAcr/8eO8v/ODrN/zM0zf83N9D/NjfP/zY3z/82N8//NjfP/zY3z/83OM//NTPM/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/NzjP/zY3z/82N8//NjfP/zY3z/82OM//ODXP/zY00P83OsL/NizZ/zs9xf9AQLz/HzjW/xAAuP/f2////v////r7///7+//////////+/////P////z//+vt//9ZWdj/AAa9/y44z/8zOtH/KzvM/y47y/84OM//PDXP/zItxf8yKqL/5eL///v////7//r//f/8//3+/v///f7///38//j79//s7v//FwCi/zIf4P83MOr/MjvG/zM2yv83Msz/PDzF/zQ31/8cMMP/NTi6/+by//////////3////////+////+f/////+////////qKTw/xcgv/80Ncz/NDjM/zM1yv83Ns3/MTTI/zIyy/8yM83/MjPM/zIzzP8yM8z/MjPM/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPM/zY3z/81Ns7/NTbO/zU2zv81Ns7/NDfO/zY0z/84M8//OTnN/zc20f85Ocb/PjTk/wAAsP+bn+X/9vn///3/+//8/////P////////////////7//+jq//9dWd3/LR7T/y0xzf8vO87/LjnL/y02yf80Md3/NzTS/0c90f8qCar/vLf5///////4/v//+v////v9///7/P//+v/7//r+///l4///HgCn/z4q0v86Psv/LjjF/zM7x/84O8r/NjjN/zY6zv8hKNn/HSe+/9Xi//////////3////9/////////////////f/3+/r/p6D3/wAAtf8zN9D/NTjJ/zg4z/81N8r/NzfO/zI1yv8zM8z/MzTO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP82N8//NTbO/zU2zv81Ns//NjbP/zQ3z/83N8v/OTbM/zs2z/84Oc//PDTS/xIAtP+Cjtb/8v////v8///8//j////////+/////////f7//+Xg//88N7//GiS8/zAvz/8zNtH/LzrK/y02zf8tOc7/KTLB/z041/8fAKv/oZjn//z////6//7/+f////n////4////9v///+z5///a4f//AACn/0Ax3v84Nsr/NTLR/zA2zf8zOND/NzfM/zg6z/8uMs3/AACp/8bN///6///////3///9/////v///Pv///r4/f/4+v3/mpXq/xEAwf8oNOj/MzrI/zg7yf80Ncf/NjnL/zEzyv8zNsr/MzPM/zM0zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/NjfP/zU2zv81Ns//NjbM/zA2zP85M87/MzfN/zAy0v87QL3/QjnV/yYSyv9ba87/6f3///7//////f////7////9//////v/+/r//9/R//8XEbT/IyXF/zU2zP8tOMj/KznK/ys5z/8sOMr/KDPI/zI91P8VCLb/h4Pb//j3///7/Pz//P/8//n////5//v/+f/6//T+///Bxv//AACi/0JC4/8rMMz/MjrK/zMx1f8zPL7/MzXQ/zo6z/8uL9D/DBO9/8C++v///v///v////P//////f/////////////+/P//joXl/wwUtv8nN9T/QTfL/zM2x/80Nsj/NjnP/zc2zv8yNMr/MzbK/zMzy/8zNM7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPM/zY3z/81Ns7/NTbP/zg2y/8qOsb/OjTQ/zYx1v8MPsj/NTHc/wAJtv9fY8P/9/v///7///////7////9///7/////P//+ff//727//8AAK7/MDLS/zc5zv85N83/LTnK/yQ6yf80OMf/MzPE/zM85f8AALX/bHHT/+74///+//////7/////+v/9/////////+34//+Onu7/AACt/zst5f8xOML/LDXJ/zM4zf8wNNL/OTvG/0VGwf8mMdL/AACr/6+0/////f////3////////8////+v/+///7///+////eHvj/wsAuv8wM9H/MzbO/zc2zf82Nc3/NzrO/zEzyf8yNMn/MzbN/zM2y/8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP82N8//NTbO/zc4zf8xNNT/LzDa/zow1P80N8j/Hz3Q/wAAxf9ia8D/8/3///n+/v///vz///7////////9//z/+Pv//7au//8AAKj/HRfN/zM20v83N8n/OTfM/zc1y/87P8D/MDfD/zc93P8AALP/Zm3M/+Xz///0/v///f3////9/////vz///7///Hw//91dNX/AAC1/y4r1P8zM8r/Njq//zE4xv80Nsr/NzrQ/zEzyv8sM9L/AACv/7G5+//6/P////3////9//////////7////+///5////cnDX/wAArv81Ntr/MjPO/zIzzf8xMs7/MjbL/zI0y/8zNsz/MzbL/zMzzv8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/NjfP/zU2zv8xMMz/MjTJ/zM5y/8xO8f/Pj/S/wAAt/91hNH/8vn///7/+//8/f/////9///////4/P//8fr//3581/8dALL/OzzT/zE60P8zOc7/NjnM/zg2yv83OND/NC20/0I33v8AALL/io3b//L6///2/v//+f////7//P/7/Pz/+vj///Xu//9cVsT/Jie8/zYw1/84M87/NjHT/zYw2P80NM7/OjzQ/x8ft/88Ptr/AACm/7/L///3+//////////9/////f/////////+///79f//VlXF/wASuv8+Q8n/MTHR/zMzzv8zM87/MzTN/zMzzv8zM87/MzPO/zMzzv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP8yM83/MzTO/zM0zf8zNM3/MTLM/zQ2zv85Oc//MDbP/y4yzf87Obr/Ni7t/wAApv+ZnuP/9/v///j+///9/v7///77///7///9//z/8Pn//4GC0v8AALH/NTfc/ykz2P8lO8X/MTrG/zo50P85NMr/NzTO/zg43/8iHLL/oZ7q//T5///7/////v////3//v/9/v7//fv////7//9aVMf/JyfC/xQZuf84Ocz/OjXP/zszzf86OMv/NDfJ/zI2zf8oLs3/AAC2/9Ph///y9v///v////v9/////P////3////////x7/3/QEDL/x0cwf86QND/NTPG/zg1y/8yNsz/MzbL/zMzzv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP81NtD/NTbN/zI0yv8zNM7/MjPM/zY1z/86NdL/NDjI/zE2zf8tOtL/TDb0/wsAsf+0vO3/+P/////+///+//7//v7////7///8/v//9Pr//4aE4/8AB6n/Mj3d/y42zP8qNdD/MD3G/zI2yv87Psv/MT3P/wApwf8qH6v/0Mj///n8///9//////3////+///+/////P///+z2//9NWcL/JCXB/ykw0/8vQr7/Mjy4/zww0/80OcX/JzjN/0BC4P8lJMP/Qji2/+jl///4/v///v////7////7/v//+f7///7+///49P//UDrA/wkbxv8zONH/MzLL/zU3xP81NMz/MjbM/zM2y/8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/NzjP/zQ1zP8yL8r/MjPN/zExzP82Nsv/NDfN/zk22P84NdD/OTPS/wAArv/H0v7/9v7///z9///////////+/////v////3//f///6Gi7f8AALH/FCy9/zQ60f8wOM//MTfL/y42yv87Q87/KznZ/x0lxP8tLqr/3Nf///78//////3//v/+//z///////////7///H1//9dY9T/ABi6/z9F3v8sMsb/NDbH/z0z0P89NtD/LT/J/xQ03f8jH8D/enLb//Tz/////////v////7////9/////f////3/+v/z8f//WEjF/xMSvP8yONH/MDbO/y800P8xN8T/MzbN/zMzzv8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPM/zc4z/8zNM//MzTO/zc2zf82OND/MTbN/zc8yv85MdP/QjnI/zswsv/Z3v//8/////j////7/v///v7///7+/f/8/P3//////8rE//8AAKL/L0DO/zg32P8yM87/NTvQ/zI3z/85P9H/LjjO/xQayf9WYMj/7u7///7////8//r//v/9//3//P/6//7//v/+//35//+PjOz/EADJ/zcw6f8vNsP/MzvK/zsz0f86NcP/NjzM/yAu0P8AE7T/oqf3//Hy/////////f7///7////9/////P7///z+///4/P//aGDE/yAHyP8qPMn/MjLN/zE2zv8xNM7/LzjJ/zQyz/8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP82OM//NTfN/zk50P8wNs7/OTnR/zQ30P8nNtH/MirN/0lAtf/g5f//+f/9//r+///7//7//P////78///9//j///7//+ra//8AAKP/TkXq/y48s/8uOMn/LjLP/y82zf8zOdP/PULg/wAAtf9wfdH/9Pf///j8///6/f///f/9//3//P/9//3////8//z9///Gw/7/Hg2z/yIk3P8wMNL/MTnG/zU5xv8tNMz/J0HS/x022/8AAKr/xMn///f4///+///////+///+/v/+/////v7///39///6/P//l5bh/xkUvP8sM+H/OTu//y800P8xNc3/MTXO/zA1y/80M87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM8z/NzXO/zY00P84NdH/NDrP/zE3z/8uN9f/MinM/1tZw//m5////P3/////+v/+//3//v/9//z+////+///+vz///Xy//9cU9D/JSzK/zI1zf8zMsL/LzjM/zc60/83O8j/P0TU/wAArf+Jkt7/9/z///3+/v/9/////P////3//f/8//v//P/8////+//m6P//KC6w/yspxv8+OtH/MTfM/zM2zv8yO8T/Nz/M/zAw4/8AAKb/zdb//////////////f///////f////7//v/////8///09P7/4OL//xAVuf8tMtP/LDLP/zY3w/8wNM//MTXN/zE1zf8wNs7/NDPN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPM/zU1z/8wM8z/NTXR/zY21v83Ntf/JiXL/2diyf/j6P//+//////+//////z////6/////f/9/v7//f3///78//+2tf//HBTD/ygzzP8mM8b/MzfN/zQ50v87O8v/Nzbh/wAAsf+Qk+j//P3///7+/v/9/f3//v7+//3//v/9//3//P/7//z/+//29v//gn7i/xsjwf84Pc//PDLL/y810P81ONL/Njfa/y0r1v8AAKr/2N7///n9///+//r//v/9//7//f/+//3//v/9//3//////P//+/v//09Ivf8eJ83/MjbP/zI2zf8wNMz/MTXO/zE1zf8xNc3/MDbN/zQzzf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzP81N87/MjnN/zA4y/88NNn/MCi7/1JPy//q7f//+P7///3//v/////////9////+/////3///7////////t6f//ODjF/zQl1v8wOM7/LjfL/y43zP82QNT/ODnU/wAAvf+Gi+T///z////9///9/f3//f39///+///+/f///f////v/+v/5+v7/1dH//xoAtv81M+D/MjTL/zgz0v8zN9D/NzrQ/yol2f8AEaz/197///f3///////////9//3//P/9//3//f/9//3//P/9//v//fz//7Gu9f8mFcL/LTfR/zE1zf8xNc3/MTXO/zE1zf8xNc3/MTXN/zA2zf80M83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTO/zIzzv8xMs3/NDbO/zI40f8qNdT/ODDO/0tBt//j6P///v7///7///////7////9/////f////z////9///+////////sK39/x8Zuv87Ntz/NDfN/zQ6zf8zOM//Mz3S/wAAuf9zb9f///v////8/////v///////////////////v7///7//f/9//7/+fT//29p1f8kKMz/KCnD/zM20P8zNM3/Nj7K/zEy1v8AALH/rLz///z7/////f////z////+/P/+//3//f/9//3//f/9//7//f////X4//9HN77/IirY/zA2y/8xNc3/MTXN/zE1zf8xNc3/MTXN/zE1zf8wNs3/NDPN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTO/zUzy/83Nsz/NjXL/zY2zv8zNs7/LDrV/yUPr//e3v//9/z//////v///////////////f////7////9//7//f/+/f///fX//0E7z/8lL8n/ODnP/zc0y/8gP8r/PUDS/y0s0v9QT7T/8/H////5///+/////v///////v///////////////v////3//P/+/+De//8eE7X/HCjQ/zg8zv80NM//NDjN/z1B2f8fHcD/h43u//T7///9+v3//Pz9///8/////f/////+//7//f/+//3//f////b5///Fyv7/HB7B/ywx0P8xNs3/MTXN/zE1zf8xNc3/MTXN/zE1zf8xNc3/MDbN/zQzzf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zI0zv80M8z/NjbK/zQ0yv84OM7/OzrX/wAAp/+5t/7//v////7+//////////////////////7//////////f/+/v7//vz//9XM//8WAL//JDvb/z43yv8zOMf/KDvC/y401v8AAKH/8e3////////9/vz//v/7/////f////7//////////////v////7///b7//+Pk+v/IRnH/zY11f83OMz/MTbH/zs+2f8jHMb/RUfD/+vu///8+f7//v7+//7+/////v////7///////////3////9//7//v/4+///XF3E/xgzyf85NMr/LzTO/zE1zf8xNc3/MTXN/zE1zf8xNc3/MTXN/zA2zf80M83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM7/NDPM/zU2yv82N83/KifB/ygnwv90eNr/9Pr////////+/v///v////////////////////////////3///////z6//90cNv/JyTL/y032P87NND/Lj3M/zozy/8JG7T/sbD6//r5///9/f3///////7+/v////////////////////////7////9///y9v//Q0a7/ywp0f83NtX/NjnM/zU3yf86OeD/FhSy/8fN///7//////3///7+/v/////////////////////////+/////v/+////7u7//x0Atv8yO9L/MTrJ/zIzzf8wNc3/MTXN/zE1zf8xNc3/MTXN/zA1zf8vNs3/NDPN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTO/zMzzP84Nsr/NjTM/zw41f8GALr/3Ob///n/+P////v//f/+//3////////////////////////////9///////19vz/JCjK/zE22P80NdL/MjTT/zI81v8lItL/QEe2//j6///9//z//v/8/////////v////7///////////////////3+///7/v//5ej//xQasP8vMeD/MzLO/zU2yv86OdD/GiC9/2x11v/1/v////7//////////////////////////////////////////////v3//8/J/f8mHMb/OjXY/yg4x/82N9D/MDTM/zA1zf8wNc3/MDXN/zA1zf8zNs3/MTbN/zQzzf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zI0zv80NMv/NTPL/zw4x/8LF77/m6D9//b+///////////7//3//f/9//7////+///////+/////v///////f/7+/7/4uL//wYZyP8oLcv/NDXQ/zM10P82Q9z/DxzM/+Hh///8/P///v/7//7//P////////7////+///////////////////+/f///P3//8XG//8RGLv/KTHa/zI1zv8vN8j/LTTb/x0qqP/i6v//+v7///////////////////////////////////////////////////37//+Kgc7/LSrQ/z8v2f8nNsz/NjfP/y80zP8zNs3/MjbN/zI2zf8xNs3/NDPN/zMzzf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM3/NTTO/zMxzf8yMMz/ECS2/9/s///+/v7//v7+/////v/+//7//v/+/////v///////f////3///////3//Pz//8vH//8cI8L/NznV/zM4zv86O9P/HCzL/yUxtf/+/P////z///////////7///////////////////////////////////3////+//+ysf//FxnD/zA31/8yO8z/IyrG/xYoxf+JkNn///////z8/P/////////////////////////////////////////////////8+v//a2O9/ykn1/8+NtD/KzfQ/zU3zv8xNcz/NDPN/zQzzf80M83/MzPN/zU0zf81NM3/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjPN/zM3zf81MND/IRvF/5uj8//1//z///////////////////////////////////////3////9//7////9//3////Avvn/HiTD/zE00v83PNH/MDbN/wgSu//K1f//+vz////8/////v/////////////////////////////////////////9/////v//nJzv/xocw/81N9T/LjbO/zA73P8AAKD/4+j////////9/f3//////////////////////////////////////////////////Pr//11Ysv8oKNX/PDXP/ys2zf81N8//MTXM/zQzzf8zNM3/MzTN/zI0zf83NM3/NzTN/zI0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zEzzf81NM7/OjfS/wcat//f5f///P/4///////////////////////////////////////9/////f/+/////P/6/f//w776/xsiw/8yNdP/OjzR/yMpyP8nMLT/8vf///r//f///f7//////////////////////////////////////////////f///////5KS5f8gIsb/NzPY/ys00P8ZJMj/ZWvL//b6//////////////////////////////////////////////////////////////z6//9aVK//KSjW/zw30f8rOcv/NTbQ/zE1zf80M83/MzTN/zI0zf8xNM3/NjTN/zY0zf8xNM3/MjTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIzzf80Ns3/MjLM/zc1yf9XXcz/9vv//////////////////////////////////////////////f////z////+//3/+f3//8TA9/8WH8X/NjDR/zo0yP8XHsj/n6Xs//n5///8//z////8//////////////////////////////////////////////3///////+Tk+b/IyHF/zU21v8pNtT/AA+0/73A///4//3////////////////////////////////////////////////////////////8+///WVas/y0t2P88OM3/KzfK/zU1zv8xNcv/NDPO/zI0zf81Ncz/MzXM/zY1zP82Ncz/MzXM/zU1zP8yNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8xMs3/NjjQ/zU51v8gFbP/wrr///r+///7//3//v7////+//////////////////////////////3////7/////P////r//f/U0f3/FhjG/zkt0/8zKsT/AAzE/+3u/////////f79//7+/f/////////////////////////////////////////////+///+/f//l5jm/x0YwP8yNtP/IjDN/zU0tf/2+f//9P35/////////////////////////////////////////////////////////////Pv//2lotf8qLND/OzjL/ys5yf81OMz/MTTJ/zMzzv81Ncz/NjLP/zYyz/81Ms//NTLP/zYyz/83Mc//MjXM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yM87/NDXK/zQ3zv8yMdD/Niq5/+zq/////v///v/7//7+/////v/////////////////////////////9//7/+/////v+///6//z/5ef//xsRwP8wKc7/Kh/K/x8qtf/5+/////////7+/v/+/v7//////////////////////////////////////////////////f///7W7+v8YFbb/LS3R/x0gy/91c9v/+fz///r+//////////////////////////////////////////////////////////////z9//+MkMv/GyHA/z86zv8qOMz/MTjM/zE0yf8yM87/NDXM/zYxz/82Ns//NTLO/zUyzv82Nc//NzXP/zI0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MjbL/zc3zP8zNcz/MC/L/1lPyf/19/////3/////+P///v////7//////////////////////////////f/9//z//v/7/f//+f/6//L3/P9KQtb/Hh/E/yAZ0P9NWcT/+Pv//////////////////////////////////////////////////////////////v/+//3//f/V3///Gh2x/yYU0f8oIMn/p6f5//r+///9///////////////////////////////////////////////////////////////8/v//y9T//yIrv/8/Pc7/LzfR/zM1zP8vNcn/NTPP/zM0zv83Ncz/LzXM/zYyz/82Ms//MTXM/zI0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzbL/zI0zf81N83/MDTO/ysrxf+UjOj////////9//////r//v7////+//////////////////////////////7//f/9//7//P7///z/+v/+//7/iIL1/xYbw/8AAMv/h5Tp//n8//////////////////////////////////////////////////////////////z//f/+//v/7/j//0BDvf8nG9L/CACx/8nI///7/////v/+/////////////////////////////////////////////////////////////f///+31//8XJ63/LCzG/zg81v8zM8j/MzbK/zYzzf8yM8v/ODTO/zE0zP83Nc//NzXP/zI0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzbL/zM1yv8zNcr/MjTK/ysuyv84Ocr/ubb5/////////f3//f7+//3//////v////////////////////////////////7//v////7////+//3//v///8bE//8GCL//DQDP/7e8/f/6/P///v7+///////////////////////////////////////////////////////7//3////6//7///+Nj97/DxrB/xMVs//e3P/////+/////f/////////////////////////////////////////////////////////////////29///h5Ha/x4Yxv82O9H/ODTM/zc2yv83Nsr/NjbJ/zEzz/8zNM3/MjTM/zI0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM2zP8zNcr/MzXL/zM1y/8sL8r/NTXK/83K///////////9//3////9//////7////////////////////////////////////////////////////////5+f//Hxq8/wYAwv/t7f///v///////////////////////////////////////////////////////////////P/+////+//7+vn/4d///wAAnv8ZIa//7u7/////+P////z///////////////////////////////////////////////////////////////7//P79/+fy//8jGLX/NS3a/zM3yf85Msv/OTLL/zQ2yv8yNsz/NDPO/zQzzf80M83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zNsz/MzXK/zM1y/8zNcv/Ky7K/zU1yv/Z1////v///////P/+/////v/////////////////////////////////////////////////////////+///////8/6ei9P8XAKD/9PT//////////////////////////////////////////////////////////////v////7///////3///////z3//9iXrr/aWjD//v4//////v////9///////////////////////////////////////////////////////////////////+///3////dHfG/yYjyf8xNs3/ODXM/zk2zP83Ncz/MjXJ/y82zv8wNs3/LzbN/zQzzf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzbL/zM2yf8zNcr/MzXL/ywuyv82OMz/2Nb///3///////z//v////7//////////////////////////////////////////////////////////f////v/+f////////7///n7/////////////////////////////////////////////////////////////////////v/////+/////////f//9vj///r////9/////f////3////////////////////////////////////////////////////////////////+/////P/////8//P5//8AAK3/ODbV/y83zf81NMb/OjbH/zQ2zP8wNs3/MjbO/zA2zv80M8z/MzTM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zM8//MzbN/zQ2y/8pK8j/ODrM/9jW///9///////5//3//v/+//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7////9/////////////////////////////////////////////////////////////////////////////v///P//tqPt/wkJsf8tOsH/MDXW/z0zyv80Mcz/LDHN/y81y/8uNMr/NTTQ/zM0z/8zNMz/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM2y/80Nsr/Ki3H/zo8z//X1f///P//////+f/9//7//v/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+/////v////////v6//87N67/OTrS/y4u3P87M87/NDHT/y81zf8vMsr/LjLK/zU1z/8zNM//MzTM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/NDTP/ykqy/8xM8f/zs7///z//f////f//f/9//7///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////3////9///+///9////2+H//wAAs/8yMNP/QTvC/ywx1v81NtX/LzHM/y8yzP80Nc//MzTP/zM0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zQ1zv8sLcn/NTXJ/7m4/P/9//7////1/////v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v////z//////f///v/////+//X4//+wuvX/LCG//zMxxP8rN9f/NDTU/zA0yf81M9L/MjPL/zM0zP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MTTQ/yQkxf+MgO///f//////+P/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9////8/7//4WL1P8mIrH/NTvL/zVCwv85Ocn/OTXK/zM20f8yM8z/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zA0zv8sK8z/SzzH//P2///////////8/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////P////b+///v////fYDL/zMew/9BNNT/NjTN/zg/wv8zM8//MjPN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8yNM3/LjPU/yoWvP/k5P///fz///7//v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v/8//z//f/5////+f////D7//90ZtH/MiO1/z4x1f8pO7n/NTPS/zIzzv8yM8z/MjPO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MjTN/zI10/8kHL3/rKf8//j9/f/9/f////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////3////9/////f/9//3/////////7+r//3xw2f81JsT/MDfG/y8w0f8yM8z/NDfQ/zQ1yv8xMs3/MjPM/zIzzP8yM8z/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8xMcv/NTrY/xkxvf/49v////34/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////v///////////////v/x+P//jJLV/zIew/8mNbb/M0O0/zkr3P85PMP/NjbQ/zc3z/82N8//NzjP/zIzzP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/NDXM/y8x0/8ACcH/1tP/////9P/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9/v/9+v3//P///+71//+rrOv/LznC/yQgz/8rN8b/LSjc/zE4zP8zNs7/NzfP/zc4z/8yM8z/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zU1zP8pMtD/MCTT/1dX0f/1+P/////9/////f////3////9//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7//v/8////+P7//8PI+P9ZStr/MSzO/yk7v/8yMc3/ODjQ/zEyzP8yM83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zMzzv80M87/LTfO/zw4yP8AAL3/1NH////+/P///vz//////////v/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9//////////////////////////7/4+L6/3xp3v87IMz/KzLM/zQ1zf8xMsv/MTLL/zQ1zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM2y/8zNsn/NDbJ/zI1zf81Nc3/Ji3F/1lf3v/y//3/9P/5//z////+////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7v////r+///u9/v/hoPt/zI00P8wMcr/LzDK/zIzzP80Nc7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zNsz/MzXK/zQ1yv8vNM7/MTXJ/y0zyP8GE7X/rbr9//r/9/////7/9Pz/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+//+/f//9fz//6ip8/8rLMz/MDHN/y4vxf8zNM3/MDHK/zQ1zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzbM/zM1yv80NMv/MDfK/zE3zP8yNM7/MTXS/wALtP/h4/////////P6//////////////////////////////3///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////7////9/////f////7///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////3/8ff//6aw6v9DLs3/MDTT/zU2zf8zNMv/MDHL/zQ1zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM2y/8zNsn/NDXK/y84yv8wN8r/MDjL/zE0y/8mK8j/VE/N//T9//////r////////////////////////////9///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////+/////f////3////9//////////////////////////////////////////////////////////////////////////////////////////////////////////3////+////////////////////9e3//4CD5f8aJM3/DTO1/zYz0v82N9P/MTLM/zQ1zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/MzPO/zMzzv80Ms//NDbN/zU0yf8wN8v/Lyfl/ykkvv+HgOP/7vb////+/////f/////6///////9/////f////3////9/////v////7////////////////////////////////////+//7///////////////7//v/+/////////////////////////////////////////////v////7////9/////P7//////////////////////v/////////////7///++v/////9/////f////3////9/////f////3////9/////v/////////////////9/////P/+//z//P/+/P//7ez9/11h+/8XHb7/MDLI/zQ0yv8zNs3/NjfK/zQ1zf8xMsz/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTO/zMzy/80Nsn/LjbJ/y8u2P85M83/KRaz/6Cg7//8//7//vz////+//////z//f/9//3////9/////f////7////+//////////////////////////////////////////7+///7/P////////////////////////////////////////////////////////7////+/////f////z///////////3///v9///u+vv/7/n8//v////7/v7//f7///////////7////9/////f////3////9/////f////7///////////////////////7//v////z/5Ov//1hb5f8AB7T/NzzO/y8xxf8xNsf/NzbO/zU2y/82N9D/NzjP/zIzzP8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM7/MzPP/zU2y/8wNcr/MTrC/zko4P8TD7P/qaPt//T//f/8+v////3////////7/////f////3////+/////v/////////////////////////////////////9//+Ahdz/AACV/9nX/////f////////////////////////////////////////7////8////+/////v////7//7//f7///r8///k7f//PTew/0I3uv/Z3v//9fz///z//////////////////f////3////9/////f////3////+////////////////////////////6Oj//1dR2P8ADrz/PD7O/y0zwf81Ocv/NznM/zU1zf81Nsv/NTbP/zY3z/8yM8z/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zP8zMtL/NDbK/zA+uf8tM9P/MDTE/ywltf+uqvP/+v/9///9/v//////+/////n//v/5/////v////7///////////////////////////////v7+/+XmPb/AAC8/yki5f8AAJz/3t/////////////////////////////////////////+/////f////7////9////+//8//z/+v/v7P//TUK8/yAiwf8gKMH/R0HC/+Xp///9/////////////v////3//v/9/////f////3////9/////v///////////////////v//5uX9/zxIxv8AFsr/PDC1/zQ5zv84Ocr/NzXP/zY2zf82N8z/NjfL/zY30P83OM//MjPM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM0y/80OcT/LjPP/ys40P8uMNf/Eg+6/6Gj7P/2////+v3///n////7//z/+/////7////+//////////////////////z///z9//+lo///AACt/zM50f86QNf/IynC/wAAn//b3///+vv+//f+///8/////P3///z//f/8/v///f3///7/+v////r////8//z////k5///XFjL/yMhxv8yP9T/NDnO/ygiz/8yQb//0eL//////////vv//f/4//z+/v/8/v3//v/8//7//P/8//z/9P/9///8////+P//19L//y8z1P8gJML/MjjS/zI20f8zNMf/MjTL/zI1yv8yNcn/MjbM/zIyy/8yM83/MjPM/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zv8zM8v/MzXN/zUyzf8yN9H/LjTM/zQy2P8sJaz/jI7e//7////8/f////7////5//////////////////////////v+//////+uqP//AACo/zQ93f8qL8//ND3a/zg+3v85PN7/AACk/87T///3/P///v////z+/v/8//3//P/4//7/+P///v3//vz///z9///m6f//Uk69/ysiuP86Odv/MTjN/zQ4z/82M9X/GB22/yAstf/Dy///+///////9//+//f//v/8//7//P/+//z//v79///9///9/v//0tT//ysgvv8XI8f/MDHN/zIzy/8vNs//NDPM/zMzzP8zM8z/MzPL/zMzzv8zNM7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTO/zMzzv80M87/LTTH/zQ7yv81M9b/My7P/xgft/98Zd7/9/z////7////+/z///////////////////////X4//+knvf/BAC7/y472P8qNcv/LjfL/ykxxv8sM8v/IjfI/zRCxf8AAKj/s7D///Pz///9////+//+//z9////+////vr///r9///n6f//TEO9/zAsyP88Ndn/NDLU/zA2z/8xNcr/NzjO/zoz2v8vLdv/AACi/6+w+f/49/////z///7//P/+//z//f37//39/f//////xMf6/xIAv/8tONP/MDTO/y4zy/8yNs7/MDbN/zQzzv8zNM7/MzTO/zM0zv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zU2y/8tNMv/MTTL/y81yv8tMtX/Hx7E/1RKyv/i5////P/8//////////////////v7+/99feH/AACu/yM10P9JL9L/OTLQ/zIy0P80MtH/NTDT/zw5wf8yK9X/QkDo/wAAtP99b9b/8uv///r/+//6//3///r////9///p5P//SDa2/zkxzP8pNdb/MzjL/zMzz/81NND/NTjP/zc2zf81Ocn/Oj3A/zczz/8AALj/iIHr//nv///+//z//v/8//39+//9/f//0Mr//wAArP8nMtT/Li3M/zAzy/8wNs//MDbN/y82zf80M83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zM87/NTLP/y45yP8vNcz/NDXO/x410v8pMcH/AACn/8TX/////vz/9Pf7/+bu//9za9r/EQC3/zU42v8xOMv/NDLR/zUy0P83MtD/NzLQ/zYy0v81M8r/NDXP/zIyzP8zNtT/JSbH/xUXsf/J1P//6ff///T8///p6f//Qji8/ysm0f8qM9j/MTjO/zI2zv8yOM7/NjbP/zIyzP8yNsv/MTTK/zQ0y/82NM7/Nzna/wMCtf9QUM7/5+z///38///6+f//y9L//wAAsf8wM9D/MznP/zExxf81Nsz/NDbJ/zQzzv80M83/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv80Nsv/NDPO/zUyzv8sOcj/LDDT/zMx0P8gFbT/np3t/9vi//9HRsn/ISW//zEy0v8zM9D/NDPO/zE1zP81Ncz/NDXM/zQ1zP80Ncz/NTTO/zI0zP8zM8z/MDXP/y86z/8iK7r/Jh20/7G4///Y4v//Pjeu/zoyyf8wMNj/LTPS/zY3zf8yMsz/MzPM/zIzzP8zNM3/MzPO/zMzy/8yM8//MTPN/zc1zv87PNz/HSTD/yQuqP/l6v//zdL//wAKq/8qMNH/MjjI/zM1yP80OMv/MzTM/zM2yv8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzPO/zM0zf8yNM7/MzPK/zQv2P8zQLH/NDHP/yQtsv8eJrb/Ki/F/y44x/8wOMj/NDbJ/zMzy/8zNM7/MjTN/zI0zf8yNM3/MjTN/zI0zf8zNM3/MzPO/zQ1zP8wN8j/MjTP/zQyyv8qK7H/Jyiu/zUxwv81L9D/NTfO/y84yP8zNc3/MzPN/zM0zf8zNM3/MzTN/zM0zf8zNM7/MzTN/zM0zf8yM83/MTTJ/zE3zv8xNsj/Jym7/ygpu/8uNcn/MznL/zM4xv8zNsj/MzfJ/zM0zP8zNsr/MzPO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/LjTO/0Q0yv84Ldb/LzfJ/y4zz/8qNc//Mi/U/zI1y/8zMs//MzPO/zMzy/8zNM7/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zMzzv8zNsv/NDbL/zAv1v8vNM3/MTfF/zA4xf8tOMb/MjjF/zI2yP80NM3/MzPO/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zIyzf82OM//MTLU/zUy2v8yL9b/NjbQ/zI1xf8zN8f/MzTN/zM0zP8zNcr/MzbJ/zMzzv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zEzzv84N8f/MzTM/zQzz/8xM83/MjPR/zQ00P8zNMn/MzHT/zMx0v8zNcz/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM7/MzPL/zMzyv80NdD/MTLP/y83zP8tNc3/LTXN/y82yf8xN8j/NDbN/zMzzv8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MTLL/zc20f81Ns7/NTbQ/zo10P8xNcz/MzTL/zM1yv8zNcr/MzbN/zM2y/8zM87/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/MzTN/zM0zf8zNM3/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==')
iiko_icon = Image.open(BytesIO(icon_data))

with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name

root.iconbitmap(default=temp_icon_path)
os.remove(temp_icon_path)

icon = TrayIcon("SBIS-IIKOnnect", iiko_icon, menu=(
    MenuItem("Показать", lambda: update_queue.put(lambda: show_window()), default=True),
    MenuItem("Выход", lambda: update_queue.put(lambda: exit_program(icon)))))

tree = ttk.Treeview(root, columns=("login", "status"), show='headings')

tree.heading('login', text="Логин")
tree.heading('status', text="Статус")
tree.column("login", width=50, anchor='center')
tree.column("status", width=150, anchor='center')
tree.pack()

for key in iiko_connect.keys():
    tree.insert('', 'end', values=(key,))

ttk.Button(root, text="+ Добавить соединение", command=lambda: create_connection_window("")).pack()
ttk.Button(root, text="- Удалить соединение", command=remove_connection).pack()

separator = tk.Frame(root, height=2, bd=1, relief=tk.SUNKEN)
separator.pack(fill=tk.X, padx=5, pady=5)

sbis_button = ttk.Button(root, text="Соединение СБИС", command=lambda: create_connection_window("СБИС", True))
sbis_button.pack(side=tk.TOP, padx=10, pady=10)

status_label = tk.Label(root, text="Не подключено")
status_label.pack(side=tk.TOP, padx=10, pady=10)


def get_inn_by_concept(concept_name):
    inn_mapping = {'Мелконова А. А.': '010507778771',
                   'Мелконова Анастасия': '010507778771',
                   'Каблахова Д.А.': '090702462444',
                   'Мелконов Г.С.': '231216827801',
                   'ИП МЕЛКОНОВ': '231216827801'}

    return inn_mapping.get(concept_name)


async def job(iiko_connect_list, sbis_connection_list):
    log(f"Запуск цикла. Цикл запускается каждые {SECONDS_OF_WAITING} секунд.")
    doc_count = 0

    while True:
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

                    for iiko_doc in invoice_docs:
                        assert stop_event.is_set() is False, 'Программа завершила работу'

                        try:
                            iiko_doc_num = iiko_doc.get("documentNumber")
                            log(f'№{iiko_doc_num} обрабатывается...')

                            if iiko_doc.get('status') != 'PROCESSED':
                                log(f'Неактуален в IIKO. Пропуск... \n')
                                continue

                            concept_id = iiko_doc.get('conception')
                            if concept_id is None or concept_id == '2609b25f-2180-bf98-5c1c-967664eea837':
                                log(f'Без концепции в IIKO. Пропуск... \n')
                                continue

                            else:
                                concept_name = concepts.get(f'{concept_id}')
                                if 'ооо' in concept_name.lower():
                                    is_sole_trader = False
                                else:
                                    is_sole_trader = True

                            supplier = iiko.supplier_search_by_id(iiko_doc.get("supplier"))

                            if supplier.get('name') is None:
                                log(f'Мягкий чек в IIKO. Пропуск...\n')
                                continue

                            while not validate_supplier(iiko.supplier_search_by_id(iiko_doc.get("supplier"))):
                                passed = error(f"Некорректные данные поставщика:\n"
                                               f"{supplier.get('name')}\n\n"
                                               f"Исправьте данные и нажмите\n"
                                               f"[ Ещё раз ]")
                                if passed:
                                    break

                            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                            today_docs = sbis.main_query("СБИС.СписокДокументов", {"Фильтр":
                                                                                       {"ДатаС": income_date,
                                                                                        "ДатаПо": income_date,
                                                                                        "Тип": 'ДокОтгрВх'}})
                            print(today_docs)
                            sbis_doc = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)

                            if sbis_doc:
                                log(f'Документ уже обработан в СБИС. Пропуск... \n')
                                continue

                            iiko_sum = total_price

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

                            # TODO: Внедрить проверку на дату, номер, сумму и поставшика

                            with open(XML_FILEPATH, "rb") as file:
                                encoded_string = base64.b64encode(file.read())
                                base64_file = encoded_string.decode('ascii')

                            org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                            responsible = create_responsible_dict(org_info.get('store_name'))
                            org_inn = get_inn_by_concept(concept_name)
                            if is_sole_trader and org_inn is not None:
                                organisation = {"СвФЛ": {"ИНН": org_inn}}
                            else:
                                organisation = {"СвЮЛ": {"ИНН": org_info.get('inn'),
                                                         "КПП": org_info.get('kpp')}}

                            params = {"Документ": {"Тип": "ДокОтгрВх",
                                                   "Регламент": {"Идентификатор": sbis.regulations_id},
                                                   'Номер': iiko_doc_num,
                                                   "Примечание": supplier.get('name'),
                                                   "Ответственный": responsible,
                                                   "НашаОрганизация": organisation,
                                                   "Вложение": [
                                                       {'Файл': {'Имя': XML_FILEPATH, 'ДвоичныеДанные': base64_file}}]
                                                   }}

                            agreement = sbis.search_agr(supplier['inn'])

                            if agreement is None or agreement == 'None':
                                new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)

                                log(f"Договор с ИНН №{supplier['inn']} не найден в СБИС."
                                    f"Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")
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

                                new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                                sbis.agreement_connect(agreement["Идентификатор"], new_sbis_doc["Идентификатор"])

                                log(f"Договор №{supplier['inn']} прикреплён к документу №{new_sbis_doc['Номер']}.")

                            os.remove(XML_FILEPATH)

                            update_queue.put(lambda: update_iiko_status(iiko_login, '✔ Подключено'))

                            doc_count += 1
                            log(f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

                        except Exception as e:
                            logging.warning(f'Ошибка при обработке документа: {e} | {traceback.format_exc()}')
                            continue

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


root.after(400, process_queue)

stop_event = threading.Event()
new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
update_queue = Queue()
thread.start()

asyncio.run_coroutine_threadsafe(job(iiko_connect, sbis_connect), new_loop)

icon.run_detached()
root.mainloop()
