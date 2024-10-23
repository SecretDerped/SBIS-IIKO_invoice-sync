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
                   "method": '����.�����������������',
                   "params": {"�����": login, "������": password},
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
                critical(f"�� ������� �������������� � ����.", exc_info=True)
                update_sbis_status(login, '(!) ������', "red")

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
                update_sbis_status(sid['login'], '? ����������', 'green')
                time.sleep(0.2)
                return json.loads(res.text)['result']

            case 401:
                info('��������� ���������� ������.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(sid['login'], sid['password'])
                res = niquests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']

            case 500:
                status_label.config(text=f'! ������ ! {sid["login"]}')

                text = f"������ � ����������� � ����. ������ ����������. ��� 500",
                show_notification(text)

                raise AttributeError(f'{method}: Check debug logs.')

    def search_doc(self, num, doc_type, doc_date):

        assert any(map(str.isdigit, num)), '���� �� ������ ����� �������� �� ������, � ������� ��� ����'

        params = {"������": {"�����": num,
                             "�����": doc_date,  # '17.01.2024'
                             "������": doc_date,  # '17.01.2024'
                             "���": doc_type}}
        res = self.main_query("����.����������������", params)

        return None if len(res['��������']) == 0 else res['��������'][0]

    def search_agr(self, inn):
        if inn is not None:
            assert any(map(str.isdigit, inn)), '���� �� ������ ����� ������� �� ������, � ������� ��� ����'

            params = {"������": {"�����": inn,
                                 "�����": '01.01.2020',
                                 "������": date.today().strftime('%d.%m.%Y'),
                                 "���": "����������"}}
            res = self.main_query("����.����������������", params)

            return None if len(res['��������']) == 0 else res['��������'][0]
        return None

    def agreement_connect(self, agr_id: str, doc_id: str):

        params = {
            "��������": {
                '��������': '�������',
                "�������������": agr_id,
                "�����������������": {
                    "��������": {
                        '��������': '�������',
                        "�������������": doc_id}}}}

        self.main_query("����.����������������", params)

    def get_today_docs(self, income_date, doc_type):

        params = {"������": {"�����": income_date,
                             "������": income_date,
                             "���": doc_type,
                             "���������": {"��������������": '200'}}}

        res = self.main_query("����.����������������", params)
        return None if len(res['��������']) == 0 else res['��������']
