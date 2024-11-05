from utils.db import Connection, Session, Base, engine, IIKOConnection, SABYConnection

# Создание таблиц в базе
Base.metadata.create_all(engine)


def get_connections_data():
    with Session() as session:
        return session.query(Connection).all()


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


