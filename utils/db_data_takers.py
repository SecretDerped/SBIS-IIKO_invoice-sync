from utils.db import Connection, Session, Base, engine, IIKOConnection, SABYConnection

# �������� ������ � ����
Base.metadata.create_all(engine)


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


def get_iiko_accounts():
    with Session() as session:
        return session.query(IIKOConnection).all()


def get_saby_accounts():
    with Session() as session:
        return session.query(SABYConnection).all()


def add_to_db(model):
    with Session() as session:
        session.add(model)
        session.commit()
