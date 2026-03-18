import os
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def wait_for_db():
    """Ждем пока БД будет готова"""
    host = os.getenv('DB_HOST', 'postgres-flight')
    port = os.getenv('DB_PORT', '5432')
    user = os.getenv('DB_USER', 'flight_user')
    password = os.getenv('DB_PASSWORD', 'flight_pass')
    
    for i in range(30):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database='postgres'
            )
            conn.close()
            print("Database is ready!")
            return True
        except Exception as e:
            print(f"Waiting for database... ({i+1}/30)")
            time.sleep(2)
    return False

def run_migrations():
    if not wait_for_db():
        print("Database not ready, exiting")
        return
    
    # Подключаемся к PostgreSQL
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-flight'),
        port=os.getenv('DB_PORT', '5432'),
        user=os.getenv('DB_USER', 'flight_user'),
        password=os.getenv('DB_PASSWORD', 'flight_pass'),
        database='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Создаем базу данных если её нет
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'flight_db'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE flight_db OWNER flight_user")
        print("Database flight_db created")
    
    cur.close()
    conn.close()
    
    # Подключаемся к созданной базе
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-flight'),
        port=os.getenv('DB_PORT', '5432'),
        user=os.getenv('DB_USER', 'flight_user'),
        password=os.getenv('DB_PASSWORD', 'flight_pass'),
        database='flight_db'
    )
    cur = conn.cursor()
    
    # Читаем и выполняем SQL из файла миграции
    migration_files = ['V1__create_types.sql', 'V2__create_tables.sql']
    
    for filename in migration_files:
        filepath = f'/app/migrations/{filename}'
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                sql = f.read()
                cur.execute(sql)
            print(f"Migration {filename} applied successfully")
        else:
            print(f"Migration file {filename} not found")
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    run_migrations()