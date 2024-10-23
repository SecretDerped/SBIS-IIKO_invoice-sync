import hashlib
import json
import re
import time
from datetime import date
from logging import info, debug, warning

import niquests
import xmltodict

from utils.tools import cryptokey, iiko_server_address, NoAuth


class IIKOManager:
    def __init__(self, iiko_connect_list):
        self.connect_list = iiko_connect_list
        self.server_address = iiko_server_address
        self.cryptokey = cryptokey
        self.login = None
        self.include_v2 = False

    def get_auth(self, password):
        login = self.login
        password_hash = (hashlib.sha1(password.encode())).hexdigest()
        url = f'https://{iiko_server_address}:443/resto/api/auth?login={login}&pass={password_hash}'
        res = niquests.get(url)

        info(f'Method: get_auth() | Code: {res.status_code} \n')
        debug(f'URL: {url} \n'
              f'Result: {res.text}')

        match res.status_code:

            case 200:
                info(f'Авторизация в IIKO прошла. {login}: вход выполнен.')
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
            info(f'Аккаунт IIKO - {login}: авторизуемся...')
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

        res = niquests.get(url, params)

        info(f'Method: GET {method} | Code: {res.status_code}')
        debug(f'URL: {url} \n'
              f'Parameters: {params} \n'
              f'Result: {res.text}')

        match res.status_code:

            case 200:
                update_queue.put(lambda: update_iiko_status(iiko_account.get('login'), f'? Подключено'))
                time.sleep(0.3)
                return res.text

            case 401:
                params['key'] = self.get_auth(iiko_account.get('password'))
                res = niquests.get(url, params)
                return res.text

            case _, *code:
                warning(f'Code: {code}, Method: GET {method}, response: {res.text}')
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
