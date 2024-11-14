import sqlite3

from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, event
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.engine import Engine

# Настройка подключения к базе данных. Создаём пул подключений
DATABASE_URL = 'sqlite:///connections.db'
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)

# Создаем подключение к базе данных (файл my_database.db будет создан)
connection = sqlite3.connect('connections.db')
connection.close()
Base = declarative_base()


class SABYConnection(Base):
    __tablename__ = "saby_connections"
    id = Column(Integer, primary_key=True)
    login = Column(String)
    password_hash = Column(String)
    regulation_id = Column(String)
    token = Column(String)

    # Связь с таблицей connections
    connections = relationship("Connection", back_populates="saby_connection",
                                   cascade="delete")


class IIKOConnection(Base):
    __tablename__ = "iiko_connections"
    id = Column(Integer, primary_key=True)
    login = Column(String)
    password_hash = Column(String)
    server_url = Column(String)
    token = Column(String)

    # Связь с таблицей connections
    connections = relationship("Connection", back_populates="iiko_connection",
                                   cascade="delete")


class Connection(Base):
    __tablename__ = 'connections'

    id = Column(Integer, primary_key=True)
    iiko_connection_id = Column(Integer, ForeignKey('iiko_connections.id'))
    iiko_connection = relationship('IIKOConnection',
                                   back_populates='connections')

    saby_connection_id = Column(Integer, ForeignKey('saby_connections.id'))
    saby_connection = relationship('SABYConnection',
                                   back_populates='connections')
    status = Column(String)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
