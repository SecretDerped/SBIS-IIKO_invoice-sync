import asyncio
import base64
import logging
import os
import traceback
from datetime import datetime, timedelta
from logging import info, warning
import threading

import xmltodict
from pyexpat.errors import messages

from gui.error import get_answer_from_user
from gui.main_menu import update_iiko_status
from managers.iiko import IIKOManager
from managers.saby import SBISManager
from utils.programm_loop import update_queue
from utils.tools import saby_connections, iiko_connections, validate_supplier, search_doc_days, conceptions_ignore, \
    xml_buffer_filepath, NoAuth, get_digits, create_xml_file


# ЕСЛИ ВНЕСЕНА НОВАЯ ОРГАНИЗАЦИЯ, НАДО В ТОЧНОСТИ ДО ПРОБЕЛОВ ВНЕСТИ СЮДА ИМЯ КОНЦЕПЦИИ
def get_inn_by_concept(concept_name):
    inn_mapping = {'Мелконова А.А.': '010507778771',
                   'Мелконова Анастасия': '010507778771',
                   'ИП Мелконова Анастасия': '010507778771',
                   'Мелконов Г.С.': '231216827801',
                   'ИП Мелконов Г.С.': '231216827801',
                   'ИП МЕЛКОНОВ': '231216827801',
                   'ИП Журавлев С.С.': '232910490605',
                   'Богданов М.А.': '010102511000',
                   'ИП Богданов М.А.': '010102511000',
                   'Каблахова Д.А.': '090702462444',
                   'ИП Андреев И.В.': '592007906504'}

    return inn_mapping.get(concept_name)


stop_event = threading.Event()

iiko = IIKOManager(iiko_connections)
sbis = SBISManager(saby_connections)


async def job(iiko_connect_list, sbis_connection_list):
    info(f"Запуск цикла...")
    doc_count = 0
    while not stop_event.is_set():
        try:
            assert sbis_connection_list, 'Отсутствует аккаунт СБИС'
            assert sbis_reglament, 'Отсутствует идентификатор регламента документа для СБИС'
            assert iiko_connect_list, 'Отсутствуют IIKO подключения'
            assert iiko_server, 'Отсутствует адрес IIKO сервера'
            for sbis_login in sbis_connection_list.keys():
                sbis.login = sbis_login

            for iiko_login in iiko_connect_list.keys():
                info(f'Соединение с аккаунтом IIKO: {iiko_login}')
                iiko.login = iiko_login

                try:
                    concepts = iiko.get_concepts()
                    search_date = datetime.now() - timedelta(days=search_doc_days)
                    income_iiko_docs = xmltodict.parse(iiko.search_income_docs(search_date.strftime('%Y-%m-%d')))
                    assert income_iiko_docs['incomingInvoiceDtoes'] is not None, 'В IIKO нет приходных накладных'

                    invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                    if type(invoice_docs) is dict:
                        invoice_docs = [invoice_docs]

                    for iiko_doc in reversed(invoice_docs):
                        assert stop_event.is_set() is False, 'Программа завершила работу'

                        try:
                            iiko_doc["documentNumber"] = iiko_doc.get("documentNumber").replace(' ', '')
                            iiko_doc_num = iiko_doc["documentNumber"]
                            info(f'№{iiko_doc_num} от {iiko_doc.get("incomingDate")} обрабатывается...')

                            if iiko_doc.get('status') != 'PROCESSED':
                                info(f'Неактуален в IIKO. Пропуск... \n')
                                continue

                            concept_id = iiko_doc.get('conception')
                            info(f"""{concept_id = }""")
                            if concept_id is None or concept_id == '2609b25f-2180-bf98-5c1c-967664eea837':
                                info(f'Без концепции в IIKO. Пропуск... \n')
                                continue

                            else:
                                concept_name = concepts.get(f'{concept_id}')
                                info(f"""{concept_name = }""")

                                if concept_name in conceptions_ignore:
                                    info(f'Концепция в чёрном списке. Пропуск... \n')
                                    continue

                                if 'ооо' in concept_name.lower():
                                    is_sole_trader = False
                                else:
                                    is_sole_trader = True

                            supplier = iiko.supplier_search_by_id(iiko_doc.get("supplier"))
                            info(supplier)

                            if supplier.get('name') is None or supplier.get('name').lower() == 'рынок':
                                info(f'Мягкий чек в IIKO. Пропуск...\n')
                                continue

                            if stop_event.is_set():
                                break

                            while not validate_supplier(iiko.supplier_search_by_id(iiko_doc.get("supplier"))):
                                if stop_event.is_set():
                                    break
                                message = (f"Некорректные данные поставщика в IIKO:\n"
                                           f"{supplier.get('name')}\n"
                                           f"ИНН: {supplier.get('inn', 'Не заполнено')}\n"
                                           f"Доп. сведения: {supplier.get('note', '')}\n"
                                           f"\n"
                                           f"Корректно пропишите ИНН для физ. лиц\n"
                                           f"Для юр. лиц впишите КПП в карточке поставщика во вкладке \"Дополнительные сведения\" в белом прямоугольнике для текста\n"
                                           f"в формате \"КПП: 123456789\".\n"
                                           f"\n"
                                           f"Исправьте данные, подождите полминуты, и нажмите\n"
                                           f"[ Попробовать снова ]\n")
                                if get_answer_from_user(message,
                                                        'Пропустить документ',
                                                        "Попробовать снова"):
                                    break

                            if stop_event.is_set():
                                break
                            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                            sbis_doc = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)
                            if sbis_doc:
                                warning(f'Документ уже обработан в СБИС. Пропуск... \n')
                                continue

                            xml = create_xml_file(iiko_doc, supplier)

                            # Ищет документ в СБИС с такой же суммой и той же датой
                            is_copy = False
                            today_docs = sbis.get_today_docs(income_date, 'ДокОтгрВх')
                            for sbis_doc in today_docs:
                                sbis_sum = sbis_doc.get('Сумма', '0')
                                if sbis_sum == str(total_price):
                                    sbis_name = sbis_doc.get('Контрагент', '').get('СвЮЛ' or "СвФЛ", '').get(
                                        'НазваниеПолное', 'Неизвестный')
                                    if get_answer_from_user((f'Обнаружен похожий документ:\n'
                                                             f'В IIKO: {income_date} / От {supplier.get("name")} на сумму {total_price}\n'
                                                             f'В СБИС: {income_date} / От {sbis_name} на сумму {sbis_sum}'),
                                                            'Пропустить', 'Всё равно записать'):
                                        is_copy = True
                                        break
                            # Пропускает документ, если пользователь нажал "Пропустить документ"
                            if is_copy:
                                continue

                            with open(xml_buffer_filepath, "rb") as file:
                                encoded_string = base64.b64encode(file.read())
                                base64_file = encoded_string.decode('ascii')

                            org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                            # TODO: Ответсвенный снесён. Склад не учитывается. Крепится ближайший
                            # responsible = create_responsible_dict(org_info.get('store_name'))

                            org_inn = get_inn_by_concept(concept_name)
                            if is_sole_trader and org_inn is not None:
                                organisation = {"СвФЛ": {"ИНН": org_inn}}
                            else:
                                organisation = {"СвЮЛ": {"ИНН": org_info.get('inn'),
                                                         "КПП": org_info.get('kpp')}}

                                if organisation["СвЮЛ"]["ИНН"] in conceptions_ignore:
                                    info('Это внутреннее перемещение.')
                                    continue

                            params = {"Документ": {"Тип": "ДокОтгрВх",
                                                   "Регламент": {"Идентификатор": sbis.regulations_id},
                                                   'Номер': iiko_doc_num,
                                                   "Примечание": supplier.get('name'),
                                                   # TODO: Ответсвенный снесён. Склад не учитывается. Крепится ближайший
                                                   # "Ответственный": responsible,
                                                   "НашаОрганизация": organisation,
                                                   "Вложение": [
                                                       {'Файл': {'Имя': xml_buffer_filepath,
                                                                 'ДвоичныеДанные': base64_file}}]
                                                   }}

                            agreement = sbis.search_agr(supplier['inn'])
                            error_message = (f'Ошибка в номенклатуре.\n'
                                             f'Добавьте в СБИС позиции из IIKO:\n\n'
                                             f'[ Бизнес ]\n'
                                             f'[ Каталог ]\n'
                                             f'[ + ]\n'
                                             f'[ Загрузить    > ]\n'
                                             f'[ Выгрузка номенклатуры из IIKO ]\n\n\n'
                                             f'В СБИС справа внизу появится таймер, показывающий прогресс переноса позиций.\n'
                                             f'Подождите, пока всё не синхронизируется, и нажмите\n'
                                             f'[ Продолжить обработку ]')

                            if agreement is None or agreement == 'None':
                                try:
                                    new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                                    info(f"Договор с ИНН №{supplier['inn']} не найден в СБИС."
                                         f"Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")
                                except AttributeError as e:
                                    get_answer_from_user(f'{error_message}\n\nОшибка: {e}',
                                                         "", '')
                                    pass

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
                                try:
                                    new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                                    sbis.agreement_connect(agreement["Идентификатор"], new_sbis_doc["Идентификатор"])

                                    info(f"Договор №{supplier['inn']} прикреплён к документу №{new_sbis_doc['Номер']}.")
                                except AttributeError:
                                    get_answer_from_user(error_message)
                                    pass

                            os.remove(xml_buffer_filepath)

                            update_queue.put(lambda: update_iiko_status(iiko_login, '? Подключено'))

                            doc_count += 1
                            warning(
                                f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

                        except Exception as e:
                            warning(f'Ошибка при обработке документа: {e} | {traceback.format_exc()}')
                            break

                except NoAuth:
                    update_queue.put(lambda: update_iiko_status(iiko_login, 'Неверный логин/пароль'))

                except Exception as e:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(!) Ошибка'))
                    warning(f'Цикл прервался. {e} | {traceback.format_exc()}')

                except ConnectionError:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(?) Подключение...'))

        except Exception as e:
            logging.critical(f'Ошибка: {e}\n\n {traceback.format_exc()}')

        finally:
            info(f"Завершение текущего цикла. Обработано документов: {doc_count}.\n\n")
            await asyncio.sleep(1)
