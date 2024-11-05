import json
import time
from datetime import date, datetime, timedelta
from logging import info, debug, critical, warning

import niquests

from gui.error import user_has_allowed
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
        self.attribute_error_message = (f'Ошибка в номенклатуре.\n'
                                        f'Добавьте в СБИС позиции из IIKO:\n\n'
                                        f'[ Бизнес ]\n'
                                        f'[ Каталог ]\n'
                                        f'[ + ]\n'
                                        f'[ Загрузить    > ]\n'
                                        f'[ Выгрузка номенклатуры из IIKO ]\n\n\n'
                                        f'В СБИС справа внизу появится таймер, показывающий прогресс переноса позиций.\n'
                                        f'Подождите, пока всё не синхронизируется, и запустите\n'
                                        f'программу снова.')

    def auth(self, password):
        payload = {"jsonrpc": "2.0",
                   "method": 'СБИС.Аутентифицировать',
                   "params": {"Логин": self.login,
                              "Пароль": password},
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
                critical(f"Не удалось авторизоваться в СБИС.", exc_info=True)
                update_sbis_status(login, '(!) Ошибка', "red")

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
                update_sbis_status(account_data['login'], 'Подключено', 'green')
                time.sleep(0.2)
                return json.loads(res.text)['result']

            case 401:
                info('Требуется обновление токена.')
                time.sleep(1)
                self.headers['X-SBISSessionID'] = self.auth(account_data['password'])
                res = niquests.post('https://online.sbis.ru/service/', headers=self.headers,
                                    data=json.dumps(payload))
                return json.loads(res.text)['result']

            case 500:
                status_label.config(text=f'! Ошибка ! {account_data["login"]}')

                text = f"На сервере СБИС произошёл сбой.",
                show_notification(text)

                raise AttributeError(f'{method}: Check debug logs.')

    def search_doc(self, num, doc_type, doc_date):
        assert any(map(str.isdigit, num)), 'СБИС не сможет найти документ по номеру, в котором нет цифр.'

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

    def found_duplicate_and_user_passed(self, income_date, total_price, supplier):
        """ Ищет документ в СБИС с такой же суммой и той же датой"""
        info('Ищем дубликаты в СБИС...')

        today_docs = self.get_today_docs(income_date, 'ДокОтгрВх')
        for sbis_doc in today_docs:
            sbis_sum = sbis_doc.get('Сумма', '0')

            if sbis_sum == str(total_price):
                warning(f'Найден похожий документ. Ж \n')
                sbis_name = sbis_doc.get('Контрагент', '').get('СвЮЛ' or "СвФЛ", '').get(
                    'НазваниеПолное', 'Неизвестный')

                return user_has_allowed((f'Обнаружен похожий документ:\n'
                                         f'В IIKO: {income_date} / От {supplier.get("name")} на сумму {total_price}\n'
                                         f'В СБИС: {income_date} / От {sbis_name} на сумму {sbis_sum}'),
                                        'Пропустить документ', 'Всё равно записать')
        return False

    def write_doc_without_agreement(self, params, supplier):
        try:
            new_sbis_doc = self.main_query("СБИС.ЗаписатьДокумент", params)
            info(f"Договор с ИНН №{supplier['inn']} не найден в СБИС."
                 f"Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")
        except AttributeError as e:
            return user_has_allowed(f'{self.attribute_error_message}\n'
                                    f'\n'
                                    f'Ошибка: {e}',
                                    "Пропустить документ", 'Всё равно записать')

    def write_doc_with_agreement(self, params, supplier, agreement, income_date):
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
        try:
            new_sbis_doc = self.main_query("СБИС.ЗаписатьДокумент", params)
            self.agreement_connect(agreement["Идентификатор"], new_sbis_doc["Идентификатор"])

            info(f"Договор №{supplier['inn']} прикреплён к документу №{new_sbis_doc['Номер']}.")
        except AttributeError:
            return user_has_allowed(self.attribute_error_message,
                                    "Пропустить документ", 'Всё равно записать')
