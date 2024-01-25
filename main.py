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
from tkinter import ttk
from iiko_ikon import encoded
from cryptography.fernet import Fernet
from datetime import datetime, timedelta, date
from pystray import Icon as TrayIcon, MenuItem

console_out = logging.StreamHandler()
file_log = logging.FileHandler(f"application.log", mode="w")
logging.basicConfig(handlers=(file_log, console_out), level=logging.INFO,
                    format='[%(asctime)s | %(levelname)s]: %(message)s')


def start_async_loop(loop, event):
    asyncio.set_event_loop(loop)
    while not event.is_set():
        loop.run_forever()
    loop.close()


stop_event = threading.Event()
new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event, ))
update_queue = Queue()

add_window_size = "210x120"
main_windows_size = "300x380"
XML_FILEPATH = 'income_doc_cash.xml'
iiko_conn_path = 'iiko_cash.json'
sbis_conn_path = 'sbis_cash.json'

CRYPTOKEY = Fernet(b'fq1FY_bAbQro_m72xkYosZip2yzoezXNwRDHo-f-r5c=')
SECONDS_OF_WAITING = 5

#  999-240-822.iiko.it
iiko_server_address = 'city-kids-pro-fashion-co.iiko.it'


class NoAuth(Exception):
    pass


class SABYAccessDenied(Exception):
    pass


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
    root.after(100, process_queue)


def remove_connection():
    selected_item = tree.selection()
    if selected_item:
        for line in selected_item:
            value = tree.item(line, 'values')[0]
            connections.pop(value)
            tree.delete(line)
        save_data(connections, iiko_conn_path)


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
            if login in connections:
                error_label.config(text="Логин уже существует")
                error_label.pack()
                return
            tree.insert('', 'end', values=(login,))
            add_window.destroy()
            password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
            connections[login] = password_hash_string
            save_data(connections, iiko_conn_path)
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


def on_submit_sbis(login, password, window):
    if login:
        try:
            sbis_auth(login, password)
            status_label.config(text=f'✔ Подключено: {login}', fg="blue")
        except Exception:
            status_label.config(text=f'(!) Ошибка: {login}', fg="red")
        password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
        save_data({login: password_hash_string}, sbis_conn_path)
    window.destroy()


def iiko_update_status(login, new_status):
    for line in tree.get_children():
        if tree.item(line, 'values')[0] == login:
            tree.item(line, values=(login, new_status))
            break


def sbis_update_status(login, status, color):
    update_queue.put(lambda: status_label.config(text=f'{status}: {login}', fg=f'{color}'))


def show_window():
    root.deiconify()


def hide_window():
    root.withdraw()


def exit_program(the_icon):
    stop_event.set()
    root.title("Выход...")
    root.withdraw()
    the_icon.stop()
    new_loop.call_soon_threadsafe(new_loop.stop)
    thread.join()
    root.quit()
    root.destroy()
    sys.exit()


icon_data = base64.b64decode(encoded)
iiko_icon = Image.open(BytesIO(icon_data))
with tempfile.NamedTemporaryFile(delete=False, suffix='.ico') as temp_icon_file:
    temp_icon_file.write(icon_data)
    temp_icon_path = temp_icon_file.name

root = tk.Tk()
root.iconbitmap(default=temp_icon_path)
os.remove(temp_icon_path)
root.title("Соединения IIKO")
root.geometry(main_windows_size)
root.protocol('WM_DELETE_WINDOW', hide_window)

icon = TrayIcon("SBIS-IIKOnnect", iiko_icon, menu=(
    MenuItem("Показать", lambda: update_queue.put(lambda: show_window()), default=True),
    MenuItem("Выход", lambda: update_queue.put(lambda: exit_program(icon)))
                                                    ))

connections = load_data(iiko_conn_path)

tree = ttk.Treeview(root, columns=("login", "status"), show='headings')
tree.heading('login', text="Логин")
tree.heading('status', text="Статус")
tree.column("login", width=50, anchor='center')
tree.column("status", width=150, anchor='center')
tree.pack()
for key in connections.keys():
    tree.insert('', 'end', values=(key,))

ttk.Button(root, text="+ Добавить соединение", command=lambda: create_connection_window("")).pack()
ttk.Button(root, text="- Удалить соединение", command=remove_connection).pack()

separator = tk.Frame(root, height=2, bd=1, relief=tk.SUNKEN)
separator.pack(fill=tk.X, padx=5, pady=5)

sbis_button = ttk.Button(root, text="Соединение СБИС",
                         command=lambda: create_connection_window("СБИС", True))
sbis_button.pack(side=tk.TOP, padx=10, pady=10)
sbis_connect = load_data(sbis_conn_path)
status_label = tk.Label(root, text="Не подключено")
status_label.pack(side=tk.TOP, padx=10, pady=10)


def sbis_auth(sbis_login_string, sbis_password_string):
    payload = {"jsonrpc": "2.0",
               "method": 'СБИС.Аутентифицировать',
               "params": {"Логин": sbis_login_string, "Пароль": sbis_password_string},
               "protocol": 2,
               "id": 0}
    headers = {'Host': 'online.sbis.ru',
               'Content-Type': 'application/json-rpc; charset=utf-8',
               'Accept': 'application/json-rpc'}
    res = requests.post('https://online.sbis.ru/auth/service/', headers=headers,
                        data=json.dumps(payload))

    logging.info(f'Method: SBIS_auth() | Code: {res.status_code} \n')
    logging.debug(f'URL: https://online.sbis.ru/auth/service/ \n'
                  f'Headers: {headers} \n'
                  f'Result: {json.loads(res.text)}')
    sid = json.loads(res.text)['result']

    with open(f"{sbis_login_string}_sbis_token.txt", "w+") as file:
        file.write(str(sid))
    logging.debug(f'Новый токен: {sid}')

    return sid


async def job():
    while True:
        try:
            logging.info("Начало цикла...")

            iiko_connect_list = load_data(iiko_conn_path)
            assert len(iiko_connect_list) > 0, 'Отсутствуют IIKO подключения'

            sbis_connection = load_data(sbis_conn_path)
            assert len(sbis_connection) > 0, 'Отсутствует аккаунт СБИС'

            (sbis_login, sbis_hash), = sbis_connection.items()  # Запятая после (sbis_login, sbis_hash) важна
            sbis_password = CRYPTOKEY.decrypt(sbis_hash).decode()
            for iiko_login, iiko_password_hash in iiko_connect_list.items():
                iiko_password = CRYPTOKEY.decrypt(iiko_password_hash).decode()
                try:
                    def sbis_get_sid():
                        try:
                            with open(f"{sbis_login}_sbis_token.txt", "r") as file:
                                return file.read()
                        except FileNotFoundError:
                            try:
                                return sbis_auth(sbis_login, sbis_password)
                            except Exception:
                                logging.critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                                sbis_update_status(sbis_login, '(!) Ошибка', "red")

                    def sbis_main_query(method: str, params: dict):
                        sid = sbis_get_sid()
                        payload = {"jsonrpc": "2.0",
                                   "method": method,
                                   "params": params,
                                   "protocol": 2,
                                   "id": 0}

                        headers = {'Host': 'online.sbis.ru',
                                   'Content-Type': 'application/json-rpc; charset=utf-8',
                                   'Accept': 'application/json-rpc',
                                   'X-SBISSessionID': sid}

                        res = requests.post('https://online.sbis.ru/service/', headers=headers,
                                            data=json.dumps(payload))

                        logging.info(f'Method: {method} | Code: {res.status_code} \n')
                        logging.debug(f'URL: https://online.sbis.ru/service/ \n'
                                      f'Headers: {headers}\n'
                                      f'Parameters: {params}\n'
                                      f'Result: {json.loads(res.text)}')

                        match res.status_code:
                            case 200:
                                sbis_update_status(sbis_login, '✔ Подключено', 'blue')
                                return json.loads(res.text)['result']
                            case 401:
                                logging.info('Требуется обновление токена.')
                                time.sleep(1)
                                headers['X-SBISSessionID'] = sbis_auth(sbis_login, sbis_password)
                                res = requests.post('https://online.sbis.ru/service/', headers=headers,
                                                    data=json.dumps(payload))
                                return json.loads(res.text)['result']
                            case 500:
                                status_label.config(text=f'(!) Ошибка: {sbis_login}', fg="red")
                                raise AttributeError(f'{method}: Check debug logs.')

                    def search_doc(num: str, doc_type: str, doc_date: str):
                        """Ищет документ в СБИСе по номеру документа, типу и дате.

                        Номер: можно прописать частично.
                        Пример: num = 03254 найдёт № КРТД0003254

                        Тип документа:
                        "ДокОтгрВх" - поступления, "ДоговорИсх" - исходящие договоры

                        Дата: "ДД.ММ.ГГГГ".
                        Поиск документа будет выполняться по этому дню"""

                        assert any(map(str.isdigit,
                                       num)), 'СБИС не сможет найти документ по номеру, в котором нет цифр'
                        params = {
                            "Фильтр": {
                                "Маска": num,
                                "ДатаС": doc_date,  # '17.01.2024'
                                "ДатаПо": doc_date,  # '17.01.2024'
                                "Тип": doc_type
                            }
                        }
                        res = sbis_main_query("СБИС.СписокДокументов", params)
                        if len(res['Документ']) == 0:
                            return None
                        else:
                            return res['Документ'][0]

                    def search_agr(inn: str):
                        """Ищет договор в СБИСе по номеру документа.
                        В качестве номера договора используется ИНН поставщика.
                        ИНН: Состоит из 10-и или 12-и цифр строкой"""
                        if inn is not None:
                            assert any(map(str.isdigit, inn)), 'СБИС не сможет найти договор по номеру, в котором нет цифр'
                        params = {
                            "Фильтр": {
                                "Маска": inn,
                                "ДатаС": '01.01.2020',
                                "ДатаПо": date.today().strftime('%d.%m.%Y'),
                                "Тип": "ДоговорИсх"
                            }
                        }
                        res = sbis_main_query("СБИС.СписокДокументов", params)
                        if len(res['Документ']) == 0:
                            return None
                        else:
                            return res['Документ'][0]

                    def sbis_create_responsible_name(store_name):
                        """Принимает название склада IIKO в качестве аргумента и создаёт поле
                        "Ответственный" для СБИС-запроса"""
                        if store_name:
                            words = store_name.split()
                            return {
                                'Фамилия': words[0],
                                'Имя': words[1] if len(words) > 1 else '',
                                'Отчество': ' '.join(words[2:]) if len(words) > 2 else ''
                            }
                        return {}

                    def iiko_get_auth(iiko_login_string, iiko_password_string):
                        password_hash = (hashlib.sha1(iiko_password_string.encode())).hexdigest()
                        url = f'https://{iiko_server_address}:443/resto/api/auth?login={iiko_login_string}&pass={password_hash}'
                        res = requests.get(url)

                        logging.info(f'Method: get_auth() | Code: {res.status_code} \n')
                        logging.debug(f'URL: {url} \n'
                                      f'Result: {res.text}')

                        match res.status_code:
                            case 200:
                                logging.info(f'Авторизация в IIKO прошла. {iiko_login}: вход выполнен.')
                                with open(f"{iiko_login_string}_iiko_token.txt", "w+") as file:
                                    iiko_key = res.text
                                    file.write(str(iiko_key))
                                    return iiko_key
                            case 401:
                                update_queue.put(lambda: iiko_update_status(iiko_login_string, 'Неверный логин/пароль'))
                                raise NoAuth('Неверный логин/пароль. \n'
                                             'Пароль можно изменить в IIKO Office:\n'
                                             '-- [Администрирование]\n'
                                             '-- [Права доступа]\n'
                                             '-- Правой кнопкой мыши по пользователю\n'
                                             '-- [Редактировать пользователя]\n'
                                             '-- Поле "Пароль"\n'
                                             '-- [Сохранить]')
                            case _, *code:
                                update_queue.put(lambda: iiko_update_status(iiko_login_string, f'(!) Ошибка. Код: {code}'))
                                raise NoAuth(
                                    f'Код {code}, не удалось авторизоваться в IIKO. Ответ сервера: {res.text}')

                    def iiko_get_getkey():
                        try:
                            with open(f"{iiko_login}_iiko_token.txt", "r") as file:
                                return file.read()
                        except FileNotFoundError:
                            logging.info(f'Аккаунт IIKO - {iiko_login}: авторизуемся...')
                            return iiko_get_auth(iiko_login, iiko_password)

                    def iiko_get_query(method: str, params: dict = {}):
                        base_url = f'https://{iiko_server_address}:443/resto/api/'
                        url = base_url + method
                        params['key'] = iiko_get_getkey()

                        res = requests.get(url, params)
                        logging.info(f'Method: GET {method} | Code: {res.status_code} \n')
                        logging.debug(f'URL: {url} \n'
                                      f'Parameters: {params} \n'
                                      f'Result: {res.text}')

                        match res.status_code:
                            case 200:
                                update_queue.put(lambda: iiko_update_status(iiko_login, f'✔ Подключено'))
                                return res.text
                            case 401:
                                params['key'] = iiko_get_auth(iiko_login, iiko_password)
                                res = requests.get(url, params)
                                return res.text
                            case _, *code:
                                logging.warning(f'Code: {code}, Method: GET {method}, response: {res.text}')
                                update_queue.put(lambda: iiko_update_status(iiko_login, f'(!) Ошибка. Код: {code}'))
                                return f'Error {code}. See warning logs.'

                    def income_docs_search(from_date):
                        """Ищет приходные накладные IIKO с введённой даты по сегодняшний день.
                        From_date: строка формата '2005-19-01'."""
                        return iiko_get_query(f'documents/export/incomingInvoice',
                                              {'from': from_date,
                                               'to': date.today().strftime('%Y-%m-%d')})

                    def supplier_search_by_id(supplier_id: str = ''):
                        suppliers_list = xmltodict.parse(iiko_get_query('suppliers'))
                        for supplier in suppliers_list['employees']['employee']:
                            if supplier['id'] == supplier_id:
                                return {'name': (supplier.get('name')).replace('"', ''),
                                        #  Если оставить кавычки в имени, XML сломается
                                        'inn': supplier.get('taxpayerIdNumber'),
                                        'address': supplier.get('address', '-'),
                                        'cardNumber': supplier.get('cardNumber', ''),
                                        'email': supplier.get('email', '@'),
                                        'phone': supplier.get('phone', '-')}
                            else:
                                continue

                    def get_org_info_by_store_id(store_id):
                        store_dict = xmltodict.parse(iiko_get_query('corporation/stores'))  # dict
                        orgs_dict = xmltodict.parse(iiko_get_query(f'corporation/departments'))  # dict
                        for store in store_dict.get("corporateItemDtoes", {}).get("corporateItemDto", []):
                            if store.get("id") == store_id:
                                parent_id = store.get("parentId")
                                store_name = store.get("name")
                                for organisation in orgs_dict.get("corporateItemDtoes", {}).get(
                                        "corporateItemDto", []):
                                    if organisation.get("id") == parent_id:
                                        match organisation.get("type"):
                                            case "DEPARTMENT":
                                                return {'store_name': store_name,
                                                        'inn': organisation.get("taxpayerIdNumber"),
                                                        'kpp': organisation.get("code")}
                                            case "JURPERSON":
                                                jur_info = organisation.get("jurPersonAdditionalPropertiesDto", {})
                                                return {'store_name': store_name,
                                                        'inn': jur_info.get("taxpayerId"),
                                                        'kpp': jur_info.get("accountingReasonCode")}
                        return {}

                    def iiko_synchronization():
                        search_date = datetime.now() - timedelta(days=3)

                        income_iiko_docs = xmltodict.parse(income_docs_search(search_date.strftime('%Y-%m-%d')))
                        if income_iiko_docs['incomingInvoiceDtoes'] is None:
                            logging.info('Накладные не найдены.')
                            return

                        invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                        if type(invoice_docs) == dict:
                            invoice_docs = [invoice_docs]
                        for iiko_doc in invoice_docs:
                            print(stop_event.is_set())
                            if stop_event.is_set():
                                break
                            iiko_doc_num = iiko_doc.get("documentNumber")
                            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                            if iiko_doc['status'] == 'DELETED':
                                logging.info(f'№{iiko_doc_num} удалён в IIKO. Пропуск... \n')
                                continue
                            if search_doc(iiko_doc_num, 'ДокОтгрВх', income_date):
                                logging.info(
                                    f'№{iiko_doc_num} уже есть в СБИС. Пропуск... \n')
                                continue

                            else:
                                logging.info(f'№{iiko_doc_num} Не найден в СБИС.\n Создаём документ...')
                                org_info = get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                                iiko_inn = org_info.get('inn')
                                iiko_kpp = org_info.get('kpp')
                                store_name = org_info.get('store_name')
                                responsible = sbis_create_responsible_name(store_name)

                                supplier = supplier_search_by_id(iiko_doc.get("supplier"))

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
            <СвЮЛ ИННЮЛ="{supplier.get('inn')}" НаимОрг="{supplier.get('name')}"/>
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
                                    total_amount = 0

                                    items = iiko_doc['items']['item']
                                    if type(items) is dict:
                                        code = items.get('code')
                                        total_sum = items.get('sum', '0')
                                        price = items.get('price', total_sum)
                                        actual_amount = items.get('actualAmount', '0')
                                        total_price = float(total_sum)
                                        total_amount = float(actual_amount)
                                        file.write(f'''
    <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{total_sum}" СтУчНДС="{total_sum}" Цена="{price}">
      <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПокупателя"/>
      <ИнфПолФХЖ2 Значен="Товар_{item_num}" Идентиф="НазваниеПокупателя"/>
      <ИнфПолФХЖ2 Значен="&quot;Type&quot;:&quot;Товар&quot;" Идентиф="ПоляНоменклатуры"/>
      <ИнфПолФХЖ2 Значен="41-01" Идентиф="СчетУчета"/>
    </СвТов>
    <Всего НеттоВс="{int(total_amount)}" СтБезНДСВс="{total_price}" СтУчНДСВс="{total_price}"/>
  </СодФХЖ2>
</СвДокПТПрКроме>
<СодФХЖ3 СодОпер="Перечисленные в документе ценности переданы"/>
</Документ>

</Файл>''')
                                    elif type(items) is list:
                                        for item in items:
                                            code = item.get('code')
                                            total_sum = item.get('sum', '0')
                                            price = item.get('price', total_sum)
                                            actual_amount = item.get('actualAmount', '0')
                                            total_price += float(total_sum)
                                            total_amount += float(actual_amount)
                                            file.write(f'''
    <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{total_sum}" СтУчНДС="{total_sum}" Цена="{price}">
      <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПокупателя"/>
      <ИнфПолФХЖ2 Значен="&quot;Type&quot;:&quot;Товар&quot;" Идентиф="ПоляНоменклатуры"/>
      <ИнфПолФХЖ2 Значен="41-01" Идентиф="СчетУчета"/>
    </СвТов>''')
                                            item_num += 1
                                        file.write(f'''
    <Всего НеттоВс="{int(total_amount)}" СтБезНДСВс="{total_price}" СтУчНДСВс="{total_price}"/>
  </СодФХЖ2>
</СвДокПТПрКроме>
<СодФХЖ3 СодОпер="Перечисленные в документе ценности переданы"/>
</Документ>

</Файл>''')
                                with open(XML_FILEPATH, "rb") as file:
                                    encoded_string = base64.b64encode(file.read())
                                    base64_file = encoded_string.decode('ascii')

                                params = {
                                    "Документ": {
                                        "Номер": iiko_doc_num,
                                        "Вложение": [{'Файл': {'Имя': XML_FILEPATH,
                                                               'ДвоичныеДанные': base64_file}}],
                                        "Примечание": supplier.get('name'),
                                        "Ответственный": responsible,
                                        "Тип": "ДокОтгрВх",
                                        "НашаОрганизация": {
                                            "СвЮЛ": {
                                                "ИНН": iiko_inn,
                                                "КПП": iiko_kpp,
                                            }
                                        }}}

                                agreement = search_agr(supplier['inn'])
                                if agreement:
                                    logging.info(
                                        f"Найден договор №{supplier['inn']}. Присоединяем к накладной...")
                                    agreement_note = re.sub('\D', '', agreement['Примечание'])
                                    if agreement_note == '':
                                        agreement_note = '3'
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

                                    sbis_doc = sbis_main_query("СБИС.ЗаписатьДокумент", params)
                                    logging.info(
                                        f"Документ №{iiko_doc_num} подготовлен...")

                                    params = {
                                        "Документ": {
                                            'ВидСвязи': 'Договор',
                                            "Идентификатор": agreement["Идентификатор"],
                                            "ДокументСледствие": {
                                                "Документ": {
                                                    'ВидСвязи': 'Договор',
                                                    "Идентификатор": sbis_doc["Идентификатор"]}}}}

                                    sbis_main_query("СБИС.ЗаписатьДокумент", params)
                                    logging.info(
                                        f"Договор №{supplier['inn']} прикреплён.")

                                else:
                                    sbis_main_query("СБИС.ЗаписатьДокумент", params)
                                    logging.info(
                                        f"Договор №{supplier['inn']} отсутствует. Создан документ без договора с поставщиком.")

                                logging.info(f"Накладная №{iiko_doc_num} записана в СБИС.")

                                os.remove(XML_FILEPATH)

                    iiko_synchronization()
                    update_queue.put(lambda: iiko_update_status(iiko_login, '✔ Подключено'))

                except NoAuth:
                    update_queue.put(lambda: iiko_update_status(iiko_login, 'Неверный логин/пароль'))

                except Exception as e:
                    update_queue.put(lambda: iiko_update_status(iiko_login, f'(!) Ошибка'))
                    logging.warning(f'Ошибка в цикле: {e} | {traceback.format_exc()}')

        except Exception as e:
            logging.warning(f'Ошибка: {e}\n\n {traceback.format_exc()}')

        finally:
            logging.info(f"Цикл закончен. Начало нового через {SECONDS_OF_WAITING} секунд...")
            await asyncio.sleep(SECONDS_OF_WAITING)


root.after(100, process_queue)

thread.start()
asyncio.run_coroutine_threadsafe(job(), new_loop)
icon.run_detached()
root.mainloop()
