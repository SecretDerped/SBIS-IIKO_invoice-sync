import asyncio
import logging
from logging import info, warning
import traceback
import xmltodict
from datetime import datetime, timedelta

from gui.error import user_has_allowed
from managers.iiko import IIKOManager
from managers.saby import SBISManager
from utils.db_data_takers import get_connections_data, update_status
from utils.programm_loop import stop_event
from utils.tools import validate_supplier, search_doc_days, conceptions_ignore, \
    xml_buffer_filepath, NoAuth, create_sbis_xml_and_get_total_sum, create_responsible_dict


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


CONCEPT_PASS_LIST = ['ИП Андреев И.В.']
INN_IGNORE_LIST = []


async def process_documents(iiko, sbis):
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
                if user_has_allowed(message, 'Пропустить документ', "Попробовать снова"):
                    break
            if stop_event.is_set():
                break
            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
            sbis_doc = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)

            if sbis_doc:
                warning(f'Документ уже обработан в СБИС. Пропуск... \n')
                continue

            sbis_xml_base64, total_price = create_sbis_xml_and_get_total_sum(iiko_doc, supplier)

            if sbis.found_duplicate_and_user_passed(income_date, total_price, supplier):
                continue

            org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
            responsible = create_responsible_dict(org_info.get('store_name'))

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
                                   "Регламент": {"Идентификатор": sbis.regulation_id},
                                   'Номер': iiko_doc_num,
                                   "Примечание": supplier.get('name'),
                                   "Ответственный": responsible,
                                   "НашаОрганизация": organisation,
                                   "Вложение": [
                                       {'Файл': {'Имя': xml_buffer_filepath,
                                                 'ДвоичныеДанные': sbis_xml_base64}}]
                                   }}
            agreement = sbis.search_agr(supplier['inn'])
            if agreement is None or agreement == 'None':
                await sbis.write_doc_without_agreement(params, supplier)
            else:
                await sbis.write_doc_with_agreement(params, supplier, agreement, income_date)

            warning(f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

        except Exception as e:
            warning(f'Ошибка при обработке документа: {e} | {traceback.format_exc()}')
            break


def initialize_managers(connection):
    iiko_conn = connection['iiko']
    iiko = IIKOManager(iiko_conn['login'], iiko_conn['password_hash'], iiko_conn['server_url'])

    sbis_conn = connection['saby']
    sbis = SBISManager(sbis_conn['login'], sbis_conn['password_hash'], sbis_conn['regulation_id'])
    return iiko, sbis


async def job():
    info("Запуск цикла...")
    doc_count = 0
    while not stop_event.is_set():
        connections = get_connections_data()
        if not connections:
            info('Таблица соединений пуста. Жду...')
            await asyncio.sleep(1)
            return

        try:
            for connection in connections:
                iiko, sbis = initialize_managers(connection)
                conn_id = connection['id']
                try:
                    await process_documents(iiko, sbis)
                    update_status(conn_id, '✔ Подключено')
                    doc_count += 1

                except NoAuth:
                    update_status(conn_id, 'Неверный логин/пароль')
                except ConnectionError as e:
                    update_status(conn_id, f'(?) Подключение...')
                    warning(f'Ошибка соединения: {e} | {traceback.format_exc()}')
                except Exception as e:
                    update_status(conn_id, f'(!) Ошибка')
                    warning(f'Цикл прервался. {e} | {traceback.format_exc()}')

        except Exception as e:
            logging.critical(f'Ошибка: {e}\n\n {traceback.format_exc()}')

        finally:
            info(f"Завершение текущего цикла. Обработано документов: {doc_count}.\n\n")
            await asyncio.sleep(1)
