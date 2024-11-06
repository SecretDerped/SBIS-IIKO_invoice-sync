import atexit
import base64
import json
from datetime import datetime
from logging import info, INFO, StreamHandler, FileHandler, basicConfig, getLogger, WARNING
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

# Установить уровень логирования SQLAlchemy
getLogger("sqlalchemy.engine").setLevel(WARNING)


def load_conf():
    # Определяем путь к файлу конфигурации
    if getattr(sys, 'frozen', False):
        # Если приложение собрано в один файл
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
cryptokey = Fernet(main['cryptokey'])
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
            'Фамилия': words[0],
            'Имя': words[1] if len(words) > 1 else '',
            'Отчество': ' '.join(words[2:]) if len(words) > 2 else ''
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
    info("Завершение работы и освобождение ресурсов...")


def encode_password(password):
    return cryptokey.encrypt(password.encode()).decode()


def create_sbis_xml_and_get_total_sum(iiko_doc, supplier):
    doc_num = iiko_doc["documentNumber"]
    income_date = datetime.fromisoformat(iiko_doc.get("incomingDate")).strftime('%d.%m.%Y')

    with open(xml_buffer_filepath, 'w') as file:
        file.write(f'''<?xml version="1.0" encoding="WINDOWS-1251" ?>
            <Файл ВерсФорм="5.02">
        
            <СвУчДокОбор>
            <СвОЭДОтпр/>
            </СвУчДокОбор>
        
            <Документ ВремИнфПр="9.00.00" ДатаИнфПр="{income_date}" КНД="1175010" НаимЭконСубСост="{supplier.get('name')}">
            <СвДокПТПрКроме>
            <СвДокПТПр>
            <НаимДок НаимДокОпр="Товарная накладная" ПоФактХЖ="Документ о передаче товара при торговых операциях"/>
            <ИдентДок ДатаДокПТ="{income_date}" НомДокПТ="{doc_num}"/>
            <СодФХЖ1>
              <ГрузПолуч ОКПО="06525502">
                <ИдСв>
                  <СвОрг>
                    <СвЮЛ ИННЮЛ="2311230064" КПП="231001001" НаимОрг="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ &quot;ЛЕАР ГРУПП&quot;"/>
                  </СвОрг>
                </ИдСв>
                <Адрес>
                  <АдрИнф АдрТекст="г. Краснодар, ул. им. 40-летия Победы, д. 20, Строение 1, ПОМЕЩЕНИЕ 308, 350042" КодСтр="643"/>
                </Адрес>
                <Контакт Тлф="8 (861) 204-05-06" ЭлПочта="dir@le-ar.ru"/>
                <БанкРекв НомерСчета="40702810512550035771">
                  <СвБанк БИК="044525360" КорСчет="30101810445250000360" НаимБанк="Филиал &quot;Корпоративный&quot; ПАО &quot;Совкомбанк&quot; МОСКВА"/>
                </БанкРекв>
              </ГрузПолуч>
              <Продавец>
                <ИдСв>
                  <СвОрг>
                    <СвЮЛ ИННЮЛ="{supplier.get('inn')}" ''')

        if supplier.get('kpp'):
            file.write(f'''КПП="{supplier['kpp']}" ''')

        file.write(f'''НаимОрг="{supplier.get('name')}"/>
                  </СвОрг>
                </ИдСв>
                <Адрес>
                  <АдрИнф АдрТекст="{supplier.get('address')}" КодСтр="643"/>
                </Адрес>
                <Контакт Тлф="{supplier.get('phone')}" ЭлПочта="{supplier.get('email')}"/>
                <БанкРекв НомерСчета="{supplier.get('cardNumber')}">
                  <СвБанк/>
                </БанкРекв>
              </Продавец>
              <Покупатель ОКПО="06525502">
                <ИдСв>
                  <СвОрг>
                    <СвЮЛ ИННЮЛ="2311230064" КПП="231001001" НаимОрг="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ &quot;ЛЕАР ГРУПП&quot;"/>
                  </СвОрг>
                </ИдСв>
                <Адрес>
                  <АдрИнф АдрТекст="350042, г. Краснодар, ул. им. 40-летия Победы, д. 20, Строение 1, ПОМЕЩЕНИЕ 308" КодСтр="643"/>
                </Адрес>
                <Контакт Тлф="8 (861) 204-05-06" ЭлПочта="dir@le-ar.ru"/>
                <БанкРекв НомерСчета="40702810512550035771">
                  <СвБанк БИК="044525360" КорСчет="30101810445250000360" НаимБанк="Филиал &quot;Корпоративный&quot; ПАО &quot;Совкомбанк&quot; МОСКВА"/>
                </БанкРекв>
              </Покупатель>
              <Основание НаимОсн="Договор" НомОсн="{supplier.get('inn')}"/>
              <ИнфПолФХЖ1>
                <ТекстИнф Значен="{supplier.get('inn')}" Идентиф="ДоговорНомер"/>
              </ИнфПолФХЖ1>
            </СодФХЖ1>
            </СвДокПТПр>      
            <СодФХЖ2>''')
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
                <СвТов КодТов="{code}" НаимЕдИзм="шт" НалСт="без НДС" НеттоПередано="{actual_amount}" НомТов="{item_num}" ОКЕИ_Тов="796" СтБезНДС="{price_without_vat * actual_amount}" СтУчНДС="{sum}" Цена="{price}">
                  <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПоставщика"/>
                  <ИнфПолФХЖ2 Значен="{code}" Идентиф="КодПокупателя"/>
                  <ИнфПолФХЖ2 Значен="&quot;Type&quot;:&quot;Товар&quot;" Идентиф="ПоляНоменклатуры"/>
                  <ИнфПолФХЖ2 Значен="41-01" Идентиф="СчетУчета"/>
                </СвТов>''')
            item_num += 1
            file.write(f'''
                <Всего НеттоВс="{total_amount}" СтБезНДСВс="{total_without_vat}" СтУчНДСВс="{total_price}"/>
              </СодФХЖ2>
            </СвДокПТПрКроме>
            <СодФХЖ3 СодОпер="Перечисленные в документе ценности переданы"/>
            </Документ>

            </Файл>''')
    with open(xml_buffer_filepath, "rb") as file:
        encoded_string = base64.b64encode(file.read())
        base64_file = encoded_string.decode('ascii')
    os.remove(xml_buffer_filepath)

    return base64_file, total_price



