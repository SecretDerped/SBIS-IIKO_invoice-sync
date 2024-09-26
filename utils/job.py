import os
import base64
import asyncio
import logging
import xmltodict
from datetime import datetime, timedelta
from utils.utils import get_digits, create_responsible_dict, get_inn_by_concept
from utils.xml_generator import generate_xml

XML_FILEPATH = 'income_doc_cash.xml'
search_doc_days = 15


async def job(iiko, sbis, iiko_connect_list, sbis_connection_list, gui, stop_event, config):
    log = logging.getLogger(__name__)
    log.info(f"Запуск цикла. Цикл запускается каждые {config['seconds_of_waiting']} секунд.")
    xml_path = os.path.join("../cash", config['xml_filepath'])
    doc_count = 0

    while True:
        assert len(sbis_connection_list) > 0, 'Отсутствует аккаунт СБИС'

        # Так надо
        for sbis_login in sbis_connection_list.keys():
            sbis.login = sbis_login

        assert len(iiko_connect_list) > 0, 'Отсутствуют IIKO подключения'

        for iiko_login in iiko_connect_list.keys():
            log.info(f'Соединение с аккаунтом IIKO: {iiko_login}')
            iiko.login = iiko_login

            try:
                search_date = datetime.now() - timedelta(days=config['search_doc_days'])
                income_iiko_docs = xmltodict.parse(iiko.search_income_docs(search_date.strftime('%Y-%m-%d')))
                assert income_iiko_docs['incomingInvoiceDtoes'] is not None, 'В IIKO нет приходных накладных'

                invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                if type(invoice_docs) == dict:
                    invoice_docs = [invoice_docs]

                for iiko_doc in invoice_docs:
                    assert stop_event.is_set() is False, 'Программа завершила работу'

                    try:
                        iiko_doc_num = iiko_doc.get("documentNumber")
                        log.info(f'№{iiko_doc_num} обрабатывается...')

                        if iiko_doc.get('status') != 'PROCESSED':
                            log.info(f'Неактуален в IIKO. Пропуск... \n')
                            continue

                        concept_id = iiko_doc.get('conception')
                        if concept_id is None or concept_id == '2609b25f-2180-bf98-5c1c-967664eea837':
                            log.info(f'Без концепции в IIKO. Пропуск... \n')
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
                            log.info(f'Мягкий чек в IIKO. Пропуск...\n')
                            continue

                        income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                        sbis_doc: list = sbis.search_doc(iiko_doc_num, 'ДокОтгрВх', income_date)

                        if sbis_doc:
                            log.info(f'Документ уже обработан в СБИС. Пропуск... \n')
                            continue

                        log.info(f'Идёт запись в СБИС...')
                        generate_xml(config, income_date, supplier, iiko_doc_num, iiko_doc)

                        org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                        responsible = create_responsible_dict(org_info.get('store_name'))

                        if is_sole_trader and get_inn_by_concept(concept_name) is not None:
                            print('aaaaaa' + get_inn_by_concept(concept_name))
                            organisation = {"СвФЛ": {"ИНН": get_inn_by_concept(concept_name)}}
                        else:
                            organisation = {"СвЮЛ": {"ИНН": org_info.get('inn'),
                                                     "КПП": org_info.get('kpp')}}

                        with open(xml_path, "rb") as file:
                            encoded_string = base64.b64encode(file.read())
                            base64_file = encoded_string.decode('ascii')


                        params = {"Документ": {"Тип": "ДокОтгрВх",
                                               "Регламент": {"Идентификатор": sbis.regulations_id},
                                               'Номер': iiko_doc_num,
                                               "Примечание": supplier.get('name'),
                                               "Ответственный": responsible,
                                               "НашаОрганизация": organisation,
                                               "Вложение": [
                                                   {'Файл': {'Имя': XML_FILEPATH, 'ДвоичныеДанные': base64_file}}]
                                               }}

                        agreement = sbis.search_agr(supplier['inn'])

                        if agreement is None or agreement == 'None':
                            new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)

                            log.info(f"Договор с ИНН №{supplier['inn']} не найден в СБИС."
                                     f"Создан документ №{new_sbis_doc['Номер']} без договора с поставщиком.")
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
                                    "Идентификатор": agreement["Идентификатор"]}
                            }

                            new_sbis_doc = sbis.main_query("СБИС.ЗаписатьДокумент", params)
                            sbis.agreement_connect(agreement["Идентификатор"], new_sbis_doc["Идентификатор"])
                            log.info(f"Договор №{supplier['inn']} прикреплён к документу №{new_sbis_doc['Номер']}.")

                            sbis.main_query("СБИС.ЗаписатьДокумент", params)

                            log.info(f'№{sbis_doc["Номер"]} помечен в СБИС.')

                        os.remove(xml_path)

                        gui.root.after(0, gui.update_iiko_status, iiko_login, '✔ Подключено')

                        doc_count += 1
                        log.info(f"Накладная №{iiko_doc_num} от {income_date} успешно скопирована в СБИС из IIKO.\n")

                    except Exception as e:
                        log.warning(f'Ошибка при обработке документа: {e}')
                        continue

            except Exception as e:
                gui.root.after(0, gui.update_iiko_status, iiko_login, f'! Ошибка')
                log.warning(f'Цикл прервался. {e}')

            except ConnectionError:
                gui.root.after(0, gui.update_iiko_status, iiko_login, f'(?) Подключение...')

        log.info(f"Завершение текущего цикла. Обработано документов: {doc_count}.\n\n")
        await asyncio.sleep(config['seconds_of_waiting'])
