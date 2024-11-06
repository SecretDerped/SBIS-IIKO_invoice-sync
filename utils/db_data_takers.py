from logging import error
from sqlalchemy import update
from utils.db import Connection, Session, Base, engine, IIKOConnection, SABYConnection

# Создание таблиц в базе
Base.metadata.create_all(engine)


def get_connections_data():
    with Session() as session:
        connections = session.query(Connection).all()
        # Формируем список словарей с данными подключений
        result = []
        for conn in connections:
            # Проверяем, что связанные объекты не равны None
            if conn.saby_connection and conn.iiko_connection:
                result.append({
                    "id": conn.id,
                    "saby": {
                        "login": conn.saby_connection.login,
                        "password_hash": conn.saby_connection.password_hash,
                        "regulation_id": conn.saby_connection.regulation_id,
                        "token": conn.saby_connection.token,
                    },
                    "iiko": {
                        "login": conn.iiko_connection.login,
                        "password_hash": conn.iiko_connection.password_hash,
                        "server_url": conn.iiko_connection.server_url,
                        "token": conn.iiko_connection.token
                    }})
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


def update_status(conn_id, status):
    with Session() as session:
        try:
            # Обновляем статус подключения в базе данных
            session.execute(
                update(Connection)
                .where(Connection.id == conn_id)
                .values(status=status)
            )
            session.commit()

        except Exception as e:
            session.rollback()
            error(f"Ошибка при обновлении статуса подключения: {e}")
        finally:
            session.close()
