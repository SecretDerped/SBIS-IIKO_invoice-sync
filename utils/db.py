import sqlite3

from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, event
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

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
    connections = relationship("Connection", back_populates="saby_connection")


class IIKOConnection(Base):
    __tablename__ = "iiko_connections"
    id = Column(Integer, primary_key=True)
    login = Column(String)
    password_hash = Column(String)
    server_url = Column(String)
    token = Column(String)

    # Связь с таблицей connections
    connections = relationship("Connection", back_populates="iiko_connection")


class Connection(Base):
    __tablename__ = "connections"
    id = Column(Integer, primary_key=True)
    saby_connection_id = Column(Integer, ForeignKey("saby_connections.id"), nullable=False)
    iiko_connection_id = Column(Integer, ForeignKey("iiko_connections.id"), nullable=False)
    status = Column(String)

    # Устанавливаем отношения для удобного обращения к связанным данным
    saby_connection = relationship("SABYConnection", back_populates="connections")
    iiko_connection = relationship("IIKOConnection", back_populates="connections")


def db_listener_on(model, func_on_change):
    event.listen(model, 'after_insert', func_on_change)
    event.listen(model, 'after_update', func_on_change)
    event.listen(model, 'after_delete', func_on_change)
