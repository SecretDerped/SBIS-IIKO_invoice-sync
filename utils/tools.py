import atexit
import json
from datetime import datetime
from logging import info, INFO, StreamHandler, FileHandler, basicConfig
import os
import re
import sys

import tomli
from cryptography.fernet import Fernet

log_level = INFO
console_out = StreamHandler()
file_log = FileHandler(f"application.log", mode="w")
basicConfig(format='[%(asctime)s] | %(message)s',
            handlers=(file_log, console_out),
            level=log_level)


def load_conf():
    # ���������� ���� � ����� ������������
    if getattr(sys, 'frozen', False):
        # ���� ���������� ������� � ���� ����
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    config_path = os.path.join(base_path, "utils/config.toml")
    with open(config_path, 'rb') as f:
        conf = tomli.load(f)

    return conf


config = load_conf()

main = config['main']
search_doc_days = main['search_doc_days']
cryptokey = Fernet(bytes(main['cryptokey']))
xml_buffer_filepath = main['xml_buffer_filepath']
iiko_connections = main['iiko_connections_list_filepath']
saby_connections = main['saby_connections_list_filepath']

account = config['account']
iiko_server_address = account['iiko_server_address']
saby_regulation_id = account['saby_regulation_id']
conceptions_ignore = account['conceptions_ignore']
inns_ignore = account['inns_ignore']

app_gui = config['gui']
title = app_gui['main_title']
theme = app_gui['theme']

window_size = app_gui['window_size']
add_window_size = window_size['adding']
main_windows_size = window_size['main']
error_windows_size = window_size['error']


class NoAuth(Exception):
    pass


def doc_print(json_doc):
    info(json.dumps(json_doc, indent=4, sort_keys=True, ensure_ascii=False))


def get_digits(string):
    return re.sub('\D', '', string)


def create_responsible_dict(store_name):
    if store_name:
        words = store_name.split()
        return {
            '�������': words[0],
            '���': words[1] if len(words) > 1 else '',
            '��������': ' '.join(words[2:]) if len(words) > 2 else ''
        }

    return {}


def validate_supplier(supplier):
    inn = supplier.get('inn', '')
    if inn is None:
        inn = ''

    kpp = supplier.get('kpp', '')
    if kpp is None:
        inn = ''

    if len(inn) == 12 and (kpp == '' or kpp is None):
        return True
    elif len(inn) == 10 and len(kpp) == 9:
        return True
    else:
        return False


@atexit.register
def cleanup():
    info("���������� ������ � ������������ ��������...")


def save_data(data, path):
    with open(path, 'w') as file:
        json.dump(data, file)


def load_data(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as file:
                return json.load(file)

        except json.decoder.JSONDecodeError:
            os.remove(path)
            return {}

    return {}


def create_xml_file(iiko_doc, supplier):
    doc_num = iiko_doc["documentNumber"]
    income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')

    with open(xml_buffer_filepath, 'w') as file:
        file.write(f'''<?xml version="1.0" encoding="WINDOWS-1251" ?>
            <���� ��������="5.02">
        
            <�����������>
            <���������/>
            </�����������>
        
            <�������� ���������="9.00.00" ���������="{income_date}" ���="1175010" ���������������="{supplier.get('name')}">
            <��������������>
            <���������>
            <������� ����������="�������� ���������" ��������="�������� � �������� ������ ��� �������� ���������"/>
            <�������� ���������="{income_date}" ��������="{doc_num}"/>
            <������1>
              <��������� ����="06525502">
                <����>
                  <�����>
                    <���� �����="2311230064" ���="231001001" �������="�������� � ������������ ���������������� &quot;���� �����&quot;"/>
                  </�����>
                </����>
                <�����>
                  <������ ��������="�. ���������, ��. ��. 40-����� ������, �. 20, �������� 1, ��������� 308, 350042" ������="643"/>
                </�����>
                <������� ���="8 (861) 204-05-06" �������="dir@le-ar.ru"/>
                <�������� ����������="40702810512550035771">
                  <������ ���="044525360" �������="30101810445250000360" ��������="������ &quot;�������������&quot; ��� &quot;����������&quot; ������"/>
                </��������>
              </���������>
              <��������>
                <����>
                  <�����>
                    <���� �����="{supplier.get('inn')}" ''')

        if supplier.get('kpp'):
            file.write(f'''���="{supplier['kpp']}" ''')

        file.write(f'''�������="{supplier.get('name')}"/>
                  </�����>
                </����>
                <�����>
                  <������ ��������="{supplier.get('address')}" ������="643"/>
                </�����>
                <������� ���="{supplier.get('phone')}" �������="{supplier.get('email')}"/>
                <�������� ����������="{supplier.get('cardNumber')}">
                  <������/>
                </��������>
              </��������>
              <���������� ����="06525502">
                <����>
                  <�����>
                    <���� �����="2311230064" ���="231001001" �������="�������� � ������������ ���������������� &quot;���� �����&quot;"/>
                  </�����>
                </����>
                <�����>
                  <������ ��������="350042, �. ���������, ��. ��. 40-����� ������, �. 20, �������� 1, ��������� 308" ������="643"/>
                </�����>
                <������� ���="8 (861) 204-05-06" �������="dir@le-ar.ru"/>
                <�������� ����������="40702810512550035771">
                  <������ ���="044525360" �������="30101810445250000360" ��������="������ &quot;�������������&quot; ��� &quot;����������&quot; ������"/>
                </��������>
              </����������>
              <��������� �������="�������" ������="{supplier.get('inn')}"/>
              <���������1>
                <�������� ������="{supplier.get('inn')}" �������="������������"/>
              </���������1>
            </������1>
            </���������>      
            <������2>''')
        item_num = 1
        total_price = 0.0
        total_without_vat = 0
        total_amount = 0
        items = iiko_doc['items']['item']

        if type(items) is dict:
            items = [items]
        for item in items:
            code = item.get("productArticle")
            sum = float(item.get('sum', '0'))
            price = float(item.get('price', sum))
            vat_percent = float(item.get("vatPercent", '0'))
            actual_amount = float(item.get('actualAmount', '1'))
            price_without_vat = float(item.get('priceWithoutVat', price))

            total_price += sum
            total_amount += actual_amount
            total_without_vat += sum - (sum * vat_percent)

            file.write(f'''
                <����� ������="{code}" ���������="��" �����="��� ���" �������������="{actual_amount}" ������="{item_num}" ����_���="796" ��������="{price_without_vat * actual_amount}" �������="{sum}" ����="{price}">
                  <���������2 ������="{code}" �������="�������������"/>
                  <���������2 ������="{code}" �������="�������������"/>
                  <���������2 ������="&quot;Type&quot;:&quot;�����&quot;" �������="����������������"/>
                  <���������2 ������="41-01" �������="���������"/>
                </�����>''')
            item_num += 1
            file.write(f'''
                <����� �������="{total_amount}" ����������="{total_without_vat}" ���������="{total_price}"/>
              </������2>
            </��������������>
            <������3 �������="������������� � ��������� �������� ��������"/>
            </��������>

            </����>''')