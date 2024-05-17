import logging
import os
import json
import time

import requests
from datetime import datetime


class SABYAccessDenied(Exception):
    pass


class SBISManager:
    def __init__(self, sbis_connection_list, cryptokey, regulations_id):
        self.cryptokey = cryptokey
        self.regulations_id = regulations_id
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

        token_path = os.path.join("cash", f"{login}_sbis_token.txt")
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w+") as file:
            file.write(str(sid))

        return sid

    def get_sid(self):
        login = self.login
        password_hash = self.connection_list[login]
        password = self.cryptokey.decrypt(password_hash).decode()
        token_path = os.path.join("cash", f"{login}_sbis_token.txt")

        try:
            with open(token_path, "r") as file:
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
                raise

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

        logging.info(f'Method: {method} | Code: {res.status_code}')
        logging.debug(f'URL: https://online.sbis.ru/service/ \n'
                      f'Headers: {self.headers}\n'
                      f'Parameters: {params}\n'
                      f'Result: {json.loads(res.text)}')

        match res.status_code:
            case 200:
                return json.loads(res.text)['result']
            case 401:
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(sid['login'], sid['password'])
                res = requests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']
            case 500:
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
            return res['Документ'][0]

    def search_agr(self, inn):
        if inn is not None:
            assert any(map(str.isdigit, inn)), 'СБИС не сможет найти договор по номеру, в котором нет цифр'

            params = {"Фильтр": {"Маска": inn,
                                 "ДатаС": '01.01.2020',
                                 "ДатаПо": datetime.now().strftime('%d.%m.%Y'),
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
