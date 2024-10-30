from utils.db import Connection, Session, Base, engine, IIKOConnection, SABYConnection

# Создание таблиц в базе
Base.metadata.create_all(engine)


def get_connections_data():
    # Создаем сессию для выполнения запросов
    with Session() as session:
        # Выполняем запрос и загружаем все связи между Saby и IIKO
        connections = session.query(Connection).all()

        # Формируем список словарей с данными подключений
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
