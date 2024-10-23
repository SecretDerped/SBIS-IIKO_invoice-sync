import json
import time
from datetime import date
from logging import info, debug, critical

import niquests

from gui.main_menu import update_sbis_status, status_label
from gui.windows import show_notification
from utils.tools import cryptokey, saby_regulation_id


class SBISManager:
    def __init__(self, sbis_connection_list):
        self.cryptokey = cryptokey
        self.regulations_id = saby_regulation_id
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

        res = niquests.post(f'{self.base_url}/auth/service/', headers=self.headers, data=json.dumps(payload))
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
                critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                update_sbis_status(login, '(!) Ошибка', "red")

    def main_query(self, method: str, params: dict or str):
        sid = self.get_sid()
        self.headers['X-SBISSessionID'] = sid['sid']
        payload = {"jsonrpc": "2.0",
                   "method": method,
                   "params": params,
                   "protocol": 2,
                   "id": 0}

        res = niquests.post('https://online.sbis.ru/service/', headers=self.headers,
                            data=json.dumps(payload))

        info(f'Method: {method} | Code: {res.status_code}')
        debug(f'URL: https://online.sbis.ru/service/ \n'
              f'Headers: {self.headers}\n'
              f'Parameters: {params}\n'
              f'Result: {json.loads(res.text)}')

        match res.status_code:

            case 200:
                update_sbis_status(sid['login'], '? Подключено', 'green')
                time.sleep(0.2)
                return json.loads(res.text)['result']

            case 401:
                info('Требуется обновление токена.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(sid['login'], sid['password'])
                res = niquests.post('https://online.sbis.ru/service/', headers=self.headers,
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
