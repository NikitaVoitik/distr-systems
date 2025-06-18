from datetime import datetime
import os
import hashlib
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv
import pymysql

load_dotenv()


NUM_SHARDS = int(os.environ.get("NUM_SHARDS", 2))


DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "3306")
DB_NAME_BASE = os.environ.get("DB_NAME", "shifts_db")


engines = {}
shard_sessions = {}

for shard_id in range(NUM_SHARDS):
    db_name = f"{DB_NAME_BASE}_{shard_id}"

    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{db_name}"

    engines[shard_id] = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600
    )

    shard_sessions[shard_id] = sessionmaker(autocommit=False, autoflush=False, bind=engines[shard_id])

Base = declarative_base()

class ShiftsRequest(Base):
    __tablename__ = "shifts_request"

    id = Column(String(36), primary_key=True)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shift_id = Column(String(36), nullable=False)
    request_id = Column(String(36), nullable=False)
    company_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    action = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_shard_id(company_id):
    hash_value = int(hashlib.md5(company_id.encode()).hexdigest(), 16)
    return hash_value % NUM_SHARDS

def get_db_for_company(company_id):
    shard_id = get_shard_id(company_id)
    db = shard_sessions[shard_id]()
    try:
        yield db
    finally:
        db.close()

SessionLocal = shard_sessions[0]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_databases_exist():
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        port=int(DB_PORT)
    )

    try:
        with conn.cursor() as cursor:
            for shard_id in range(NUM_SHARDS):
                db_name = f"{DB_NAME_BASE}_{shard_id}"

                cursor.execute(f"SHOW DATABASES LIKE %s", (db_name,))
                result = cursor.fetchone()

                if not result:
                    # Use backticks to properly escape database names
                    cursor.execute(f"CREATE DATABASE `{db_name}`")
                    print(f"Created database {db_name}")

                    # Use backticks in the GRANT statement too
                    cursor.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{DB_USER}'@'%'")

            cursor.execute("FLUSH PRIVILEGES")
            conn.commit()
    finally:
        conn.close()


def init_db():
    ensure_databases_exist()
    for shard_id in range(NUM_SHARDS):
        Base.metadata.create_all(bind=engines[shard_id])