import re
import os
import sys
import threading
import time
import json
import base64
import hashlib
import asyncio
import pystray
import logging
import requests
import xmltodict
import tkinter as tk

from PIL import Image
from tkinter import ttk
from cryptography.fernet import Fernet
from datetime import datetime, timedelta, date

console_out = logging.StreamHandler()
file_log = logging.FileHandler(f"application.log", mode="w")
logging.basicConfig(handlers=(file_log, console_out), level=logging.DEBUG,
                    format='[%(asctime)s | %(levelname)s]: %(message)s')

icon_image = Image.open("iiko_icon.ico")  # Укажите путь к иконке
add_window_size = "210x120"
main_windows_size = "300x380"

XML_FILEPATH = 'income_doc_cash.xml'
iiko_conn_path = 'iiko_cash.json'
sbis_conn_path = 'sbis_cash.json'

CRYPTOKEY = Fernet(b'fq1FY_bAbQro_m72xkYosZip2yzoezXNwRDHo-f-r5c=')
SECONDS_OF_WAITING = 5

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
        if login:
            if password:
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
            status_label.config(text='✔ Подключено', fg="blue")
        except Exception:
            status_label.config(text='(!) Ошибка', fg="red")
        password_hash_string = CRYPTOKEY.encrypt(password.encode()).decode()
        save_data({login: password_hash_string}, 'sbis_cash.json')
    window.destroy()


def remove_connection():
    selected_item = tree.selection()
    if selected_item:
        for item in selected_item:
            value = tree.item(item, 'values')[0]
            connections.pop(value)
            tree.delete(item)
        save_data(connections, iiko_conn_path)


def create_tray_icon(root_window):
    def on_click(icon, item):
        if item == 'show':
            icon.stop()
            root_window.after(0, root_window.deiconify)
        elif item == 'exit':
            icon.stop()
            new_loop.call_soon_threadsafe(new_loop.stop)
            thread.join()
            root_window.destroy()
            sys.exit()

    def hide_window():
        root_window.withdraw()
        menu = pystray.Menu(
            pystray.MenuItem('Показать', lambda: on_click(icon, 'show'), default=True),
            pystray.MenuItem('Выход', lambda: on_click(icon, 'exit'))
        )
        icon = pystray.Icon("app_name", icon_image, "Your App", menu)
        icon.run()

    root_window.protocol("WM_DELETE_WINDOW", hide_window)
    root_window.bind("<Unmap>", lambda event: hide_window() if root_window.state() == 'iconic' else False)


def update_status(login, new_status):
    # Найти идентификатор строки для данного логина и обновить статус
    for item in tree.get_children():
        if tree.item(item, 'values')[0] == login:
            tree.item(item, values=(login, new_status))
            break


root = tk.Tk()
root.iconbitmap(default="iiko_icon.ico")
root.title("Соединения IIKO")
root.geometry(main_windows_size)

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
sbis_connect = load_data('sbis_cash.json')
status_label = tk.Label(root, text="Не подключено")
status_label.pack(side=tk.TOP, padx=10, pady=10)

create_tray_icon(root)


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
                  f'Data: {payload} \n'
                  f'Result: {json.loads(res.text)}')
    sid = json.loads(res.text)['result']

    with open("sbis_token.txt", "w+") as file:
        file.write(str(sid))
    logging.debug(f'Новый токен: {sid}')

    return sid


async def job():
    while True:
        try:
            logging.info("Job running...")
            iiko_connect_list = load_data(iiko_conn_path)
            if len(iiko_connect_list) > 0:
                for iiko_login, iiko_password_hash in iiko_connect_list.items():
                    iiko_password = CRYPTOKEY.decrypt(iiko_password_hash).decode()
                    sbis_connection = load_data(sbis_conn_path)
                    if len(sbis_connect) > 0:
                        for sbis_login_key, sbis_hash_value in sbis_connection.items():
                            sbis_login = sbis_login_key
                            sbis_password = CRYPTOKEY.decrypt(sbis_hash_value).decode()

                        def sbis_get_sid():
                            try:
                                with open("sbis_token.txt", "r") as file:
                                    return file.read()
                            except FileNotFoundError:
                                try:
                                    return sbis_auth(sbis_login, sbis_password)
                                except Exception:
                                    logging.critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                                    status_label.config(text='(!) Ошибка', fg="red")

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
                                    status_label.config(text='✔ Подключено', fg="blue")
                                    return json.loads(res.text)['result']
                                case 401:
                                    logging.info('Требуется обновление токена.')
                                    time.sleep(1)
                                    headers['X-SBISSessionID'] = sbis_auth(sbis_login, sbis_password)
                                    res = requests.post('https://online.sbis.ru/service/', headers=headers,
                                                        data=json.dumps(payload))
                                    return json.loads(res.text)['result']
                                case 500:
                                    status_label.config(text='(!) Ошибка', fg="red")
                                    raise AttributeError(f'{method}: Check debug logs.')

                        def search_doc(num: str, doc_type: str):
                            assert any(
                                map(str.isdigit, num)), 'Метод не сможет найти документ по номеру, в котором нет цифр'
                            params = {
                                "Фильтр": {
                                    "Маска": num,
                                    "ДатаС": '01.01.2003',
                                    "ДатаПо": date.today().strftime('%d.%m.%Y'),
                                    "Тип": doc_type
                                }
                            }
                            res = sbis_main_query("СБИС.СписокДокументов", params)
                            if len(res['Документ']) == 0:
                                return None
                            else:
                                return res['Документ'][0]

                        def search_agr(inn: str):
                            return search_doc(inn, "ДоговорИсх")

                        def write_income_doc(doc_number: str, filepath: str, note: str = 'Основной склад') -> dict:
                            if filepath:
                                with open(filepath, "rb") as file:
                                    encoded_string = base64.b64encode(file.read())
                                    base64_file = encoded_string.decode('ascii')
                            params = {
                                "Документ": {
                                    "Номер": doc_number,
                                    "Вложение": [{'Файл': {'Имя': filepath,
                                                           'ДвоичныеДанные': base64_file}}],
                                    'Срок': '10.01.2024',
                                    "Примечание": note,
                                    "Тип": "ДокОтгрВх"
                                }
                            }
                            return sbis_main_query("СБИС.ЗаписатьДокумент", params)

                        def iiko_get_auth(iiko_login_string, iiko_password_string):
                            password_hash = (hashlib.sha1(iiko_password_string.encode())).hexdigest()
                            url = f'https://999-240-822.iiko.it:443/resto/api/auth?login={iiko_login_string}&pass={password_hash}'
                            res = requests.get(url)

                            logging.info(f'Method: get_auth() | Code: {res.status_code} \n')
                            logging.debug(f'URL: {url} \n'
                                          f'Result: {res.text}')

                            match res.status_code:
                                case 200:
                                    with open(f"{iiko_login_string}_iiko_token.txt", "w+") as file:
                                        key = res.text
                                        file.write(str(key))
                                        return key
                                case 401:
                                    update_status(iiko_login, 'Неверный логин/пароль')
                                    raise NoAuth('Неверный логин/пароль. \n'
                                                 'Пароль можно изменить в IIKO Office:\n'
                                                 '-- [Администрирование]\n'
                                                 '-- [Права доступа]\n'
                                                 '-- Правой кнопкой мыши по пользователю\n'
                                                 '-- [Редактировать пользователя]\n'
                                                 '-- Поле "Пароль"\n'
                                                 '-- [Сохранить]')
                                case _, *code:
                                    update_status(iiko_login, f'(!) Ошибка. Код: {code}')
                                    raise NoAuth(
                                        f'Код {code}, не удалось авторизоваться в IIKO Transport. Ответ сервера: {res.text}')

                        def iiko_get_getkey():
                            try:
                                with open(f"{iiko_login}_iiko_token.txt", "r") as file:
                                    return file.read()
                            except FileNotFoundError:
                                logging.info(f'No server token file. Authorization...')
                                return iiko_get_auth(iiko_login, iiko_password)

                        def iiko_get_query(method: str, params: dict = {}):
                            base_url = 'https://999-240-822.iiko.it:443/resto/api/'
                            url = base_url + method
                            params['key'] = iiko_get_getkey()

                            res = requests.get(url, params)
                            logging.info(f'Method: GET {method} | Code: {res.status_code} \n')
                            logging.debug(f'URL: {url} \n'
                                          f'Parameters: {params} \n'
                                          f'Result: {res.text}')

                            match res.status_code:
                                case 200:
                                    update_status(iiko_login, '✔ Подключено')
                                    return res.text
                                case 401:
                                    params['key'] = iiko_get_auth(iiko_login, iiko_password)
                                    res = requests.get(url, params)
                                    return res.text
                                case _, *code:
                                    logging.warning(f'Code: {code}, Method: GET {method}, response: {res.text}')
                                    update_status(iiko_login, f'(!) Ошибка. Код: {code}')
                                    return f'Error {code}. See warning logs.'

                        def income_docs_search():
                            return iiko_get_query(f'documents/export/incomingInvoice',
                                                  {'from': '2005-09-01',
                                                   'to': date.today().strftime('%Y-%m-%d')})

                        def supplier_search_by_id(id: str = ''):
                            suppliers_list = xmltodict.parse(iiko_get_query('suppliers'))
                            for supplier in suppliers_list['employees']['employee']:
                                if supplier['id'] == id:
                                    return {'name': supplier.get('name'),
                                            'inn': supplier.get('taxpayerIdNumber'),
                                            'address': supplier.get('address', '-'),
                                            'cardNumber': supplier.get('cardNumber', ''),
                                            'email': supplier.get('email', '@'),
                                            'phone': supplier.get('phone', '-')}
                                else:
                                    continue

                        def search_store(store_id):
                            store = {'name': 'Основной склад',
                                     'code': '1'}
                            store_json = xmltodict.parse(iiko_get_query('corporation/stores'))
                            for store_info in store_json['corporateItemDtoes']['corporateItemDto']:
                                if store_info['id'] == store_id:
                                    store['name'] = store_info['name']
                                    store['code'] = store_info['code']
                                    return store
                            return store

                        def get_requisites() -> dict:
                            restaurant_info_xml = iiko_get_query(f'corporation/departments')
                            restaurant_info_json = xmltodict.parse(restaurant_info_xml)
                            return restaurant_info_json['corporateItemDtoes']['corporateItemDto'][0][
                                "jurPersonAdditionalPropertiesDto"]

                        def iiko_synchronization():

                            income_iiko_docs = xmltodict.parse(income_docs_search())
                            if income_iiko_docs['incomingInvoiceDtoes'] is None:
                                logging.info('Накладные не найдены.')
                                return

                            iiko_restourant_jurinfo = get_requisites()
                            iiko_inn = iiko_restourant_jurinfo.get("taxpayerId", '')
                            iiko_kpp = iiko_restourant_jurinfo.get("accountingReasonCode", '')
                            invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']

                            if type(invoice_docs) == dict:
                                invoice_docs = [invoice_docs]

                            for iiko_doc in invoice_docs:

                                iiko_doc_num = iiko_doc["documentNumber"]

                                if iiko_doc['status'] == 'DELETED':
                                    logging.info(f'Invoice #{iiko_doc_num} was deleted from the IIKO earlier. Pass... \n')
                                    continue

                                if search_doc(iiko_doc_num, 'ДокОтгрВх'):
                                    logging.info(f'Incoming invoice #{iiko_doc_num} is exist in the SABY.Sbis: Pass... \n')
                                    continue

                                else:
                                    logging.info(
                                        f'Incoming invoice #{iiko_doc_num} is not founded in the SABY.Sbis:\n Proceed...')
                                    income_date = datetime.fromisoformat(iiko_doc["incomingDate"]).strftime('%d.%m.%Y')
                                    store = search_store(iiko_doc["defaultStore"])
                                    supplier = supplier_search_by_id(iiko_doc["supplier"])

                                    with open(XML_FILEPATH, 'w') as file:
                                        file.write(f'''<?xml version="1.0" encoding="WINDOWS-1251" ?>
                            <Файл ВерсФорм="5.02">
        
                              <СвУчДокОбор>
                                <СвОЭДОтпр/>
                              </СвУчДокОбор>
        
                              <Документ ВремИнфПр="12.00.00" ДатаИнфПр="{income_date}" КНД="1175010" НаимЭконСубСост="{supplier['name']}">
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
                                            <СвЮЛ ИННЮЛ="{supplier['inn']}" НаимОрг="{supplier['name']}"/>
                                          </СвОрг>
                                        </ИдСв>
                                        <Адрес>
                                          <АдрИнф АдрТекст="{supplier['address']}" КодСтр="643"/>
                                        </Адрес>
                                        <Контакт Тлф="{supplier['phone']}" ЭлПочта="{supplier['email']}"/>
                                        <БанкРекв НомерСчета="{supplier['cardNumber']}">
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
                                      <Основание НаимОсн="Договор" НомОсн="{supplier['inn']}"/>
                                      <ИнфПолФХЖ1>
                                        <ТекстИнф Значен="{supplier['inn']}" Идентиф="ДоговорНомер"/>
                                        <ТекстИнф Значен="{store['code']}" Идентиф="СкладКод"/>
                                        <ТекстИнф Значен="{store['name']}" Идентиф="СкладНаименование"/>
                                      </ИнфПолФХЖ1>
                                    </СодФХЖ1>
                                  </СвДокПТПр>      
                                  <СодФХЖ2>''')
                                        item_num = 1
                                        total_price = 0
                                        total_amount = 0
                                        items = iiko_doc['items']['item']

                                        if type(items) is dict:
                                            code = items['code']
                                            sum = items['sum'] or '0'
                                            price = items['price'] or sum
                                            actual_amount = items['actualAmount'] or '0'
                                            total_price = float(sum)
                                            total_amount = float(actual_amount)
                                            file.write(f'''
                                                            <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{sum}" СтУчНДС="{sum}" Цена="{price}">
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
                                                sum = item.get('sum', '0')
                                                price = item.get('price', sum)
                                                actual_amount = item.get('actualAmount', '0')
                                                total_price += float(sum)
                                                total_amount += float(actual_amount)
                                                file.write(f'''
                                        <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{sum}" СтУчНДС="{sum}" Цена="{price}">
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

                                    agreement = search_agr(supplier['inn'])

                                    if agreement:
                                        logging.info(f"Agreement #{supplier['inn']} is founded. Connecting to invoice...")
                                        agreement_note = re.sub('\D', '', agreement['Примечание'])
                                        if agreement_note == '':
                                            agreement_note = '3'
                                        payment_days = int(agreement_note)
                                        deadline = datetime.strptime(income_date, '%d.%m.%Y') + timedelta(days=payment_days)
                                        deadline_str = datetime.strftime(deadline, '%d.%m.%Y')

                                        params = {
                                            "Документ": {
                                                "Номер": iiko_doc_num,
                                                "Вложение": [{'Файл': {'Имя': XML_FILEPATH,
                                                                       'ДвоичныеДанные': base64_file}}],
                                                "Примечание": store['name'],
                                                "Тип": "ДокОтгрВх",
                                                'ВидСвязи': 'Договор',
                                                'Срок': deadline_str,
                                                "НашаОрганизация": {
                                                    "СвЮЛ": {
                                                        "ИНН": iiko_inn,
                                                        "КПП": iiko_kpp,
                                                    }
                                                },
                                                "ДокументОснование": {
                                                    "Документ": {
                                                        'ВидСвязи': 'Договор',
                                                        "Идентификатор": agreement["Идентификатор"]}}}}
                                        sbis_doc = sbis_main_query("СБИС.ЗаписатьДокумент", params)

                                        params = {
                                            "Документ": {
                                                'ВидСвязи': 'Договор',
                                                "Идентификатор": agreement["Идентификатор"],
                                                "ДокументСледствие": {
                                                    "Документ": {
                                                        'ВидСвязи': 'Договор',
                                                        "Идентификатор": sbis_doc["Идентификатор"]}}}}
                                        sbis_main_query("СБИС.ЗаписатьДокумент", params)

                                    else:
                                        write_income_doc(iiko_doc_num, XML_FILEPATH)
                                        logging.info(
                                            f"Agreement #{supplier['inn']} is not exist. Created invoice without supplier.")
                                    logging.info(f"Document #{iiko_doc_num} is created.")

                                    os.remove(XML_FILEPATH)

                        iiko_synchronization()

        except Exception as e:
            logging.info(f"Error: {e}")

        finally:
            logging.info(f"Job completed. Starting new loop in {SECONDS_OF_WAITING} seconds...")
            await asyncio.sleep(SECONDS_OF_WAITING)


def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


# Создание нового асинхронного цикла событий
new_loop = asyncio.new_event_loop()

# Запуск асинхронного цикла событий в отдельном потоке
thread = threading.Thread(target=start_async_loop, args=(new_loop,))
thread.start()

# Создание асинхронной задачи в новом цикле событий
asyncio.run_coroutine_threadsafe(job(), new_loop)

# Запуск Tkinter цикла событий
root.mainloop()
