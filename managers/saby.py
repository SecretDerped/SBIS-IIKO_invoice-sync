import json
import time
from datetime import date, datetime, timedelta
from logging import info, debug, critical, warning

import niquests

from gui.error import user_has_allowed
from gui.main_menu import update_sbis_status, status_label
from gui.windows import show_notification
from utils.tools import cryptokey, get_digits


class SBISManager:
    def __init__(self, login, password_hash, regulation_id):
        self.login = login
        self.password_hash = password_hash
        self.regulation_id = regulation_id
        self.base_url = 'https://online.sbis.ru'
        self.headers = {'Host': 'online.sbis.ru',
                        'Content-Type': 'application/json-rpc; charset=utf-8',
                        'Accept': 'application/json-rpc'}
        self.attribute_error_message = (f'������ � ������������.\n'
                                        f'�������� � ���� ������� �� IIKO:\n\n'
                                        f'[ ������ ]\n'
                                        f'[ ������� ]\n'
                                        f'[ + ]\n'
                                        f'[ ���������    > ]\n'
                                        f'[ �������� ������������ �� IIKO ]\n\n\n'
                                        f'� ���� ������ ����� �������� ������, ������������ �������� �������� �������.\n'
                                        f'���������, ���� �� �� ����������������, � ���������\n'
                                        f'��������� �����.')

    def auth(self, password):
        payload = {"jsonrpc": "2.0",
                   "method": '����.�����������������',
                   "params": {"�����": self.login,
                              "������": password},
                   "protocol": 2,
                   "id": 0}

        res = niquests.post(f'{self.base_url}/auth/service/',
                            headers=self.headers,
                            data=json.dumps(payload))
        sid = json.loads(res.text)['result']

        with open(f"{self.login}_sbis_token.txt", "w+") as file:
            file.write(str(sid))

        return sid

    def get_account_with_sid(self):
        login = self.login
        password = cryptokey.decrypt(self.password_hash).decode()

        try:
            with open(f"{login}_sbis_token.txt") as file:
                sid = file.read()
                return {'login': login,
                        'password': password,
                        'sid': sid}

        except FileNotFoundError:
            try:
                sid = self.auth(password)
                return {'login': login,
                        'password': password,
                        'sid': sid}

            except Exception:
                critical(f"�� ������� �������������� � ����.", exc_info=True)
                update_sbis_status(login, '(!) ������', "red")

    def main_query(self, method: str, params: dict or str):
        account_data = self.get_account_with_sid()
        self.headers['X-SBISSessionID'] = account_data['account_data']
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
                update_sbis_status(account_data['login'], '����������', 'green')
                time.sleep(0.2)
                return json.loads(res.text)['result']

            case 401:
                info('��������� ���������� ������.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(account_data['password'])
                res = niquests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']

            case 500:
                status_label.config(text=f'! ������ ! {account_data["login"]}')

                text = f"�� ������� ���� ��������� ����.",
                show_notification(text)

                raise AttributeError(f'{method}: Check debug logs.')

    def search_doc(self, num, doc_type, doc_date):
        assert any(map(str.isdigit, num)), '���� �� ������ ����� �������� �� ������, � ������� ��� ����.'

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

    def found_duplicate_and_user_passed(self, income_date, total_price, supplier):
        """ ���� �������� � ���� � ����� �� ������ � ��� �� �����"""
        info('���� ��������� � ����...')

        today_docs = self.get_today_docs(income_date, '���������')
        for sbis_doc in today_docs:
            sbis_sum = sbis_doc.get('�����', '0')

            if sbis_sum == str(total_price):
                warning(f'������ ������� ��������. � \n')
                sbis_name = sbis_doc.get('����������', '').get('����' or "����", '').get(
                    '��������������', '�����������')

                return user_has_allowed((f'��������� ������� ��������:\n'
                                         f'� IIKO: {income_date} / �� {supplier.get("name")} �� ����� {total_price}\n'
                                         f'� ����: {income_date} / �� {sbis_name} �� ����� {sbis_sum}'),
                                        '���������� ��������', '�� ����� ��������')
        return False

    def write_doc_without_agreement(self, params, supplier):
        try:
            new_sbis_doc = self.main_query("����.����������������", params)
            info(f"������� � ��� �{supplier['inn']} �� ������ � ����."
                 f"������ �������� �{new_sbis_doc['�����']} ��� �������� � �����������.")
        except AttributeError as e:
            return user_has_allowed(f'{self.attribute_error_message}\n'
                                    f'\n'
                                    f'������: {e}',
                                    "���������� ��������", '�� ����� ��������')

    def write_doc_with_agreement(self, params, supplier, agreement, income_date):
        agreement_note = get_digits(agreement['����������'])
        if agreement_note == '':
            agreement_note = '7'

        payment_days = int(agreement_note)
        deadline = datetime.strptime(income_date, '%d.%m.%Y') + timedelta(
            days=payment_days)
        deadline_str = datetime.strftime(deadline, '%d.%m.%Y')

        params['��������']['����'] = deadline_str
        params['��������']['��������'] = '�������'
        params['��������']['�����������������'] = {
            "��������": {
                '��������': '�������',
                "�������������": agreement["�������������"]}}
        try:
            new_sbis_doc = self.main_query("����.����������������", params)
            self.agreement_connect(agreement["�������������"], new_sbis_doc["�������������"])

            info(f"������� �{supplier['inn']} ��������� � ��������� �{new_sbis_doc['�����']}.")
        except AttributeError:
            return user_has_allowed(self.attribute_error_message,
                                    "���������� ��������", '�� ����� ��������')
