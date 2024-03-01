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
from logging import info as log
from cryptography.fernet import Fernet
from datetime import datetime, timedelta, date
from pystray import Icon as TrayIcon, MenuItem

log_level = logging.INFO
search_doc_days = 28
SECONDS_OF_WAITING = 5

XML_FILEPATH = 'income_doc_cash.xml'
IIKO_CONN_PATH = 'iiko_cash.json'
SBIS_CONN_PATH = 'sbis_cash.json'

add_window_size = "210x120"
main_windows_size = "300x380"

iiko_server_address = 'gorod-detei-pyatigorsk.iiko.it'
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
    root.after(100, process_queue)


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


class NoAuth(Exception):
    pass


class SABYAccessDenied(Exception):
    pass


class IIKOManager:
    """Для интеграции требуется:
    - Указывать ИНН и КПП юр. лицам в IIKO. Как своей организации, так и поставщикам.
    - Код концепции должен совпадать с КПП филиала.
    - Код подразделения должен быть таким же, как КПП филиала. Необходимо для загрузки накладных как для ИП, так и для ООО.
    """
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
                update_queue.put(
                    lambda: update_iiko_status(login, f'(!) Ошибка. Код: {code}'))
                raise NoAuth(
                    f'Код {code}, не удалось авторизоваться в IIKO. Ответ сервера: {res.text}')

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
                return f'Error {code}. See warning logs.'

    def search_income_docs(self, from_date: str):
        """Ищет приходные накладные IIKO с введённой даты по сегодняшний день."""
        params = {'from': from_date,
                  'to': date.today().strftime('%Y-%m-%d')}
        return self.get_query(f'documents/export/incomingInvoice', params)

    def supplier_search_by_id(self, supplier_id: str = ''):
        suppliers_list = xmltodict.parse(self.get_query('suppliers'))
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

    def get_org_info_by_store_id(self, store_id):
        store_dict = xmltodict.parse(self.get_query('corporation/stores'))  # dict
        orgs_dict = xmltodict.parse(self.get_query(f'corporation/departments'))  # dict
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
                                        'kpp': get_digits(organisation.get("code"))}
                            case "JURPERSON":
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
    """Для нормальной работы необходимо:
    - Перекачать номенклатуру из IIKO (Бизнес > Каталог > + > Загрузить > Из iiko)
    - Настроить автопроводку поступлениям (Бизнес > Закупки/Расходы > Настройки > Операции > *Создаём заново, скопировав Поступление, или изменяем существующее* > Проведение > Документ проводить при Сохранении)
    - Код филиала у ИП должен быть таким же, как КПП филиала (Наши компании > *Выбираем компанию* > Реквизиты > Код филиала)
    - Создать договор с поставщиком (Документы > Договоры > + > Входящий договор > (Вписываем контрагента, в качестве номера документа вписываем его ИНН, в описании указываем количество дней срока оплаты*)
    - Создать склады и сотрудника на каждый склад, ФИО которых будет совпадать с его складом и прикрепить их в качестве ответственных, а также в списке "Со складом работают" вместе с нужной организацией
    """
    def __init__(self, sbis_connection_list):
        self.cryptokey = CRYPTOKEY
        self.regulations_id = sbis_regulations_id
        self.connection_list = sbis_connection_list
        self.base_url = 'https://online.sbis.ru'
        self.headers = {
            'Host': 'online.sbis.ru',
            'Content-Type': 'application/json-rpc; charset=utf-8',
            'Accept': 'application/json-rpc'
        }
        self.login = None

    def auth(self, login, password):
        self.login = login
        payload = {
            "jsonrpc": "2.0",
            "method": 'СБИС.Аутентифицировать',
            "params": {"Логин": login, "Пароль": password},
            "protocol": 2,
            "id": 0
        }
        res = requests.post(f'{self.base_url}/auth/service/', headers=self.headers,
                            data=json.dumps(payload))
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
                return {'login': login, 'password': password, 'sid': sid}
        except FileNotFoundError:
            try:
                sid = self.auth(login, password)
                return {'login': login, 'password': password, 'sid': sid}
            except Exception:
                logging.critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                update_sbis_status(login, '(!) Ошибка', "red")

    def main_query(self, method: str, params: dict or str):
        sid = self.get_sid()
        self.headers['X-SBISSessionID'] = sid['sid']
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "protocol": 2,
            "id": 0
        }

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
        params = {
            "Фильтр": {
                "Маска": num,
                "ДатаС": doc_date,  # '17.01.2024'
                "ДатаПо": doc_date,  # '17.01.2024'
                "Тип": doc_type
            }
        }
        res = self.main_query("СБИС.СписокДокументов", params)
        if len(res['Документ']) == 0:
            return None
        else:
            return res['Документ'][0]

    def search_agr(self, inn):
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

icon_data = base64.b64decode(encoded)
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
    # Да, хардкод, но дедлайн сегодня.
    inn_mapping = {
        'Мелконова А. А.': '010507778771',
        'Мелконова Анастасия': '010507778771',
        'Каблахова Д.А.': '090702462444',
        'Мелконов Г.С.': '231216827801',
        'ИП МЕЛКОНОВ': '231216827801',
    }

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
                    search_date = datetime.now() - timedelta(days=search_doc_days)
                    income_iiko_docs = xmltodict.parse(iiko.search_income_docs(search_date.strftime('%Y-%m-%d')))
                    assert income_iiko_docs['incomingInvoiceDtoes'] is not None, 'В IIKO нет приходных накладных'

                    invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                    if type(invoice_docs) == dict:
                        invoice_docs = [invoice_docs]
                    for iiko_doc in invoice_docs:
                        assert stop_event.is_set() is False, 'Программа завершила работу'

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
                            concepts = iiko.get_concepts()
                            concept_name = concepts.get(f'{concept_id}')
                            if 'ООО' in concept_name:
                                is_sole_trader = False
                            else:
                                is_sole_trader = True

                        supplier = iiko.supplier_search_by_id(iiko_doc.get("supplier"))
                        if supplier.get('name') is None:
                            log(f'Мягкий чек в IIKO. Пропуск...\n')
                            continue

                        income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                        sbis_doc = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)
                        is_copy = False
                        if sbis_doc is not None:
                            if sbis_doc['Примечание'] != '' or sbis_doc['Расширение']['Проведен'] == 'Да':
                                log(f'Документ уже обработан в СБИС. Пропуск... \n')
                                continue
                            log(f'Требуется копия.')
                            is_copy = True

                        log(f'Идёт запись в СБИС...')
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
                            total_without_vat = 0
                            total_amount = 0
                            items = iiko_doc['items']['item']
                            if type(items) is dict:
                                items = [items]
                            for item in items:
                                code = item.get("productArticle")

                                actual_amount = float(item.get('actualAmount', '1'))
                                sum = float(item.get('sum', '0'))
                                vat_percent = float(item.get("vatPercent", '0'))
                                price = float(item.get('price', sum))
                                price_without_vat = float(item.get('priceWithoutVat', price))

                                total_without_vat += sum - (sum * vat_percent)
                                total_price += sum
                                total_amount += actual_amount
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
                        with open(XML_FILEPATH, "rb") as file:
                            encoded_string = base64.b64encode(file.read())
                            base64_file = encoded_string.decode('ascii')
                        org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                        responsible = create_responsible_dict(org_info.get('store_name'))
                        if is_sole_trader and get_inn_by_concept(concept_name) is not None:
                            organisation = {"СвФЛ": {"ИНН": get_inn_by_concept(concept_name),
                                                     "КодФилиала": org_info.get('kpp')}}
                        else:
                            organisation = {"СвЮЛ": {"ИНН": org_info.get('inn'),
                                                     "КПП": org_info.get('kpp')}}

                        params = {
                            "Документ": {
                                "Тип": "ДокОтгрВх",
                                "Вложение": [{'Файл': {'Имя': XML_FILEPATH, 'ДвоичныеДанные': base64_file}}],
                                "Регламент": {"Идентификатор": sbis.regulations_id},
                                'Номер': iiko_doc_num,
                                "Примечание": supplier.get('name'),
                                "Ответственный": responsible,
                                "НашаОрганизация": organisation}}
                        if is_copy:
                            params["Документ"]['Номер'] = sbis_doc['Номер']
                            params["Документ"]['Примечание'] += ', копия'

                        agreement = sbis.search_agr(supplier['inn'])
                        if agreement is None or agreement == 'None':
                            new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                            log(
                                f"Договор с ИНН №{supplier['inn']} не найден в СБИС. Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")
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

                        if is_copy:
                            params = {
                                "Документ": {
                                    "Идентификатор": sbis_doc["Идентификатор"],
                                    "Примечание": 'Копия внесена'}}
                            sbis.main_query("СБИС.ЗаписатьДокумент", params)
                            log(f'№{sbis_doc["Номер"]} помечен в СБИС.')

                        os.remove(XML_FILEPATH)
                        update_queue.put(lambda: update_iiko_status(iiko_login, '✔ Подключено'))
                        doc_count += 1
                        log(f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

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


root.after(100, process_queue)
stop_event = threading.Event()
new_loop = asyncio.new_event_loop()
thread = threading.Thread(target=start_async_loop, args=(new_loop, stop_event,))
update_queue = Queue()
thread.start()
asyncio.run_coroutine_threadsafe(job(iiko_connect, sbis_connect), new_loop)
icon.run_detached()
root.mainloop()
