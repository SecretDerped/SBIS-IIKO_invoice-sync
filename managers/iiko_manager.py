import os
import json
import hashlib
import requests
import xmltodict
from datetime import datetime


class NoAuth(Exception):
    pass


class IIKOManager:
    def __init__(self, iiko_connect_list, server_address, cryptokey):
        self.connect_list = iiko_connect_list
        self.server_address = server_address
        self.cryptokey = cryptokey
        self.login = None
        self.include_v2 = False

    def get_auth(self, password):
        login = self.login
        password_hash = (hashlib.sha1(password.encode())).hexdigest()
        url = f'https://{self.server_address}:443/resto/api/auth?login={login}&pass={password_hash}'
        res = requests.get(url)

        match res.status_code:
            case 200:
                token_path = os.path.join("cash", f"{login}_iiko_token.txt")
                os.makedirs(os.path.dirname(token_path), exist_ok=True)
                with open(token_path, "w+") as file:
                    iiko_key = res.text
                    file.write(str(iiko_key))
                    return iiko_key
            case 401:
                raise NoAuth('Неверный логин/пароль.')
            case _, *code:
                raise NoAuth(f'Код {code}, не удалось авторизоваться в IIKO. Ответ сервера: {res.text}')

    def get_key(self):
        login = self.login
        iiko_hash = self.connect_list[f'{login}']
        password = self.cryptokey.decrypt(iiko_hash).decode()
        token_path = os.path.join("cash", f"{login}_iiko_token.txt")

        try:
            with open(token_path, "r") as file:
                iiko_key = file.read()
                return {'login': login, 'password': password, 'key': iiko_key}
        except FileNotFoundError:
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

        match res.status_code:
            case 200:
                return res.text
            case 401:
                params['key'] = self.get_auth(iiko_account.get('password'))
                res = requests.get(url, params)
                return res.text
            case _, *code:
                return f'Error {code}. See warning logs.'

    def search_income_docs(self, from_date: str):
        params = {'from': from_date,
                  'to': datetime.now().strftime('%Y-%m-%d')}
        return self.get_query(f'documents/export/incomingInvoice', params)

    def supplier_search_by_id(self, supplier_id: str = ''):
        suppliers_list = xmltodict.parse(self.get_query('suppliers'))

        for supplier in suppliers_list['employees']['employee']:
            if supplier['id'] == supplier_id:
                return {
                    'name': (supplier.get('name')).replace('"', ''),
                    'inn': supplier.get('taxpayerIdNumber'),
                    'address': supplier.get('address', '-'),
                    'cardNumber': supplier.get('cardNumber', ''),
                    'email': supplier.get('email', '@'),
                    'phone': supplier.get('phone', '-')
                }

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
                                return {
                                    'store_name': store_name,
                                    'inn': jur_info.get("taxpayerId"),
                                    'kpp': jur_info.get("accountingReasonCode")
                                }

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

