import os
import re
import json
from cryptography.fernet import Fernet


def load_config(path):
    with open(path, 'r') as file:
        return json.load(file)


config = load_config('config.json')


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


def get_inn_by_concept(concept_name):
    inn_mapping = {'Мелконова А. А.': '010507778771',
                   'Мелконова Анастасия': '010507778771',
                   'Каблахова Д.А.': '090702462444',
                   'Мелконов Г.С.': '231216827801',
                   'ИП МЕЛКОНОВ': '231216827801'}

    return inn_mapping.get(concept_name)


def encrypt(data):
    return Fernet(config["cryptokey"]).encrypt(data.encode()).decode()


def decrypt(data):
    return Fernet(config["cryptokey"]).decrypt(data.encode()).decode()
