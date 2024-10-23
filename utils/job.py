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


# ���� ������� ����� �����������, ���� � �������� �� �������� ������ ���� ��� ���������
def get_inn_by_concept(concept_name):
    inn_mapping = {'��������� �.�.': '010507778771',
                   '��������� ���������': '010507778771',
                   '�� ��������� ���������': '010507778771',
                   '�������� �.�.': '231216827801',
                   '�� �������� �.�.': '231216827801',
                   '�� ��������': '231216827801',
                   '�� �������� �.�.': '232910490605',
                   '�������� �.�.': '010102511000',
                   '�� �������� �.�.': '010102511000',
                   '��������� �.�.': '090702462444',
                   '�� ������� �.�.': '592007906504'}

    return inn_mapping.get(concept_name)


stop_event = threading.Event()

iiko = IIKOManager(iiko_connections)
sbis = SBISManager(saby_connections)


async def job(iiko_connect_list, sbis_connection_list):
    info(f"������ �����...")
    doc_count = 0
    while not stop_event.is_set():
        try:
            assert sbis_connection_list, '����������� ������� ����'
            assert sbis_reglament, '����������� ������������� ���������� ��������� ��� ����'
            assert iiko_connect_list, '����������� IIKO �����������'
            assert iiko_server, '����������� ����� IIKO �������'
            for sbis_login in sbis_connection_list.keys():
                sbis.login = sbis_login

            for iiko_login in iiko_connect_list.keys():
                info(f'���������� � ��������� IIKO: {iiko_login}')
                iiko.login = iiko_login

                try:
                    concepts = iiko.get_concepts()
                    search_date = datetime.now() - timedelta(days=search_doc_days)
                    income_iiko_docs = xmltodict.parse(iiko.search_income_docs(search_date.strftime('%Y-%m-%d')))
                    assert income_iiko_docs['incomingInvoiceDtoes'] is not None, '� IIKO ��� ��������� ���������'

                    invoice_docs = income_iiko_docs['incomingInvoiceDtoes']['document']
                    if type(invoice_docs) is dict:
                        invoice_docs = [invoice_docs]

                    for iiko_doc in reversed(invoice_docs):
                        assert stop_event.is_set() is False, '��������� ��������� ������'

                        try:
                            iiko_doc["documentNumber"] = iiko_doc.get("documentNumber").replace(' ', '')
                            iiko_doc_num = iiko_doc["documentNumber"]
                            info(f'�{iiko_doc_num} �� {iiko_doc.get("incomingDate")} ��������������...')

                            if iiko_doc.get('status') != 'PROCESSED':
                                info(f'���������� � IIKO. �������... \n')
                                continue

                            concept_id = iiko_doc.get('conception')
                            info(f"""{concept_id = }""")
                            if concept_id is None or concept_id == '2609b25f-2180-bf98-5c1c-967664eea837':
                                info(f'��� ��������� � IIKO. �������... \n')
                                continue

                            else:
                                concept_name = concepts.get(f'{concept_id}')
                                info(f"""{concept_name = }""")

                                if concept_name in conceptions_ignore:
                                    info(f'��������� � ������ ������. �������... \n')
                                    continue

                                if '���' in concept_name.lower():
                                    is_sole_trader = False
                                else:
                                    is_sole_trader = True

                            supplier = iiko.supplier_search_by_id(iiko_doc.get("supplier"))
                            info(supplier)

                            if supplier.get('name') is None or supplier.get('name').lower() == '�����':
                                info(f'������ ��� � IIKO. �������...\n')
                                continue

                            if stop_event.is_set():
                                break

                            while not validate_supplier(iiko.supplier_search_by_id(iiko_doc.get("supplier"))):
                                if stop_event.is_set():
                                    break
                                message = (f"������������ ������ ���������� � IIKO:\n"
                                           f"{supplier.get('name')}\n"
                                           f"���: {supplier.get('inn', '�� ���������')}\n"
                                           f"���. ��������: {supplier.get('note', '')}\n"
                                           f"\n"
                                           f"��������� ��������� ��� ��� ���. ���\n"
                                           f"��� ��. ��� ������� ��� � �������� ���������� �� ������� \"�������������� ��������\" � ����� �������������� ��� ������\n"
                                           f"� ������� \"���: 123456789\".\n"
                                           f"\n"
                                           f"��������� ������, ��������� ���������, � �������\n"
                                           f"[ ����������� ����� ]\n")
                                if get_answer_from_user(message,
                                                        '���������� ��������',
                                                        "����������� �����"):
                                    break

                            if stop_event.is_set():
                                break
                            income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')
                            sbis_doc = sbis.search_doc(iiko_doc_num, '���������', income_date)
                            if sbis_doc:
                                warning(f'�������� ��� ��������� � ����. �������... \n')
                                continue

                            xml = create_xml_file(iiko_doc, supplier)

                            # ���� �������� � ���� � ����� �� ������ � ��� �� �����
                            is_copy = False
                            today_docs = sbis.get_today_docs(income_date, '���������')
                            for sbis_doc in today_docs:
                                sbis_sum = sbis_doc.get('�����', '0')
                                if sbis_sum == str(total_price):
                                    sbis_name = sbis_doc.get('����������', '').get('����' or "����", '').get(
                                        '��������������', '�����������')
                                    if get_answer_from_user((f'��������� ������� ��������:\n'
                                                             f'� IIKO: {income_date} / �� {supplier.get("name")} �� ����� {total_price}\n'
                                                             f'� ����: {income_date} / �� {sbis_name} �� ����� {sbis_sum}'),
                                                            '����������', '�� ����� ��������'):
                                        is_copy = True
                                        break
                            # ���������� ��������, ���� ������������ ����� "���������� ��������"
                            if is_copy:
                                continue

                            with open(xml_buffer_filepath, "rb") as file:
                                encoded_string = base64.b64encode(file.read())
                                base64_file = encoded_string.decode('ascii')

                            org_info = iiko.get_org_info_by_store_id(iiko_doc.get("defaultStore"))
                            # TODO: ������������ �����. ����� �� �����������. �������� ���������
                            # responsible = create_responsible_dict(org_info.get('store_name'))

                            org_inn = get_inn_by_concept(concept_name)
                            if is_sole_trader and org_inn is not None:
                                organisation = {"����": {"���": org_inn}}
                            else:
                                organisation = {"����": {"���": org_info.get('inn'),
                                                         "���": org_info.get('kpp')}}

                                if organisation["����"]["���"] in conceptions_ignore:
                                    info('��� ���������� �����������.')
                                    continue

                            params = {"��������": {"���": "���������",
                                                   "���������": {"�������������": sbis.regulations_id},
                                                   '�����': iiko_doc_num,
                                                   "����������": supplier.get('name'),
                                                   # TODO: ������������ �����. ����� �� �����������. �������� ���������
                                                   # "�������������": responsible,
                                                   "���������������": organisation,
                                                   "��������": [
                                                       {'����': {'���': xml_buffer_filepath,
                                                                 '��������������': base64_file}}]
                                                   }}

                            agreement = sbis.search_agr(supplier['inn'])
                            error_message = (f'������ � ������������.\n'
                                             f'�������� � ���� ������� �� IIKO:\n\n'
                                             f'[ ������ ]\n'
                                             f'[ ������� ]\n'
                                             f'[ + ]\n'
                                             f'[ ���������    > ]\n'
                                             f'[ �������� ������������ �� IIKO ]\n\n\n'
                                             f'� ���� ������ ����� �������� ������, ������������ �������� �������� �������.\n'
                                             f'���������, ���� �� �� ����������������, � �������\n'
                                             f'[ ���������� ��������� ]')

                            if agreement is None or agreement == 'None':
                                try:
                                    new_sbis_doc = sbis.main_query("����.����������������", params)
                                    info(f"������� � ��� �{supplier['inn']} �� ������ � ����."
                                         f"������ �������� �{new_sbis_doc['�����']} ��� �������� � �����������.")
                                except AttributeError as e:
                                    get_answer_from_user(f'{error_message}\n\n������: {e}',
                                                         "", '')
                                    pass

                            else:
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
                                    new_sbis_doc = sbis.main_query("����.����������������", params)
                                    sbis.agreement_connect(agreement["�������������"], new_sbis_doc["�������������"])

                                    info(f"������� �{supplier['inn']} ��������� � ��������� �{new_sbis_doc['�����']}.")
                                except AttributeError:
                                    get_answer_from_user(error_message)
                                    pass

                            os.remove(xml_buffer_filepath)

                            update_queue.put(lambda: update_iiko_status(iiko_login, '? ����������'))

                            doc_count += 1
                            warning(
                                f"��������� �{iiko_doc_num} �� {income_date} ������� ����������� � ���� �� IIKO.\n")

                        except Exception as e:
                            warning(f'������ ��� ��������� ���������: {e} | {traceback.format_exc()}')
                            break

                except NoAuth:
                    update_queue.put(lambda: update_iiko_status(iiko_login, '�������� �����/������'))

                except Exception as e:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(!) ������'))
                    warning(f'���� ���������. {e} | {traceback.format_exc()}')

                except ConnectionError:
                    update_queue.put(lambda: update_iiko_status(iiko_login, f'(?) �����������...'))

        except Exception as e:
            logging.critical(f'������: {e}\n\n {traceback.format_exc()}')

        finally:
            info(f"���������� �������� �����. ���������� ����������: {doc_count}.\n\n")
            await asyncio.sleep(1)
