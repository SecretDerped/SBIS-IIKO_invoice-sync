from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from utils.db import Connection

# ��������� ����������� � ���� ������
DATABASE_URL = 'sqlite:///connections.db'
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def get_connections_data():
    # ������� ������ ��� ���������� ��������
    with Session() as session:
        # ��������� ������ � ��������� ��� ����� ����� Saby � IIKO
        connections = session.query(Connection).all()

        # ��������� ������ �������� � ������� �����������
        result = []
        for connection in connections:
            result.append({
                "id": connection.id,
                "saby": {
                    "login": connection.saby_connection.login,
                    "password_hash": connection.saby_connection.password_hash,
                    "regulation_id": connection.saby_connection.regulation_id,
                    "token": connection.saby_connection.token,
                },
                "iiko": {
                    "login": connection.iiko_connection.login,
                    "password_hash": connection.iiko_connection.password_hash,
                    "server_url": connection.iiko_connection.server_url,
                    "token": connection.iiko_connection.token
                }
            })

    return result
