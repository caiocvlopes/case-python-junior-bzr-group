import psycopg2
import time

# Tenta conectar ao banco de dados até 10 vezes
print("Iniciando setup do banco de dados...")
time.sleep(1)
for i in range(10):
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="dados",
            user="postgres",
            password="postgres",
            connect_timeout=1
        )
        print("Conexão estabelecida com sucesso.")
        break

    except psycopg2.OperationalError as e:
        if i == 9:
            raise RuntimeError(
                "Não foi possível conectar ao banco de dados após 10 tentativas."
            ) from e

        print(f"Aguardando banco de dados... ({i + 1}/10)")
        time.sleep(1)

try:
    with conn.cursor() as cursor:
        with open("schema.sql", "r", encoding="utf-8") as file:
            cursor.execute(file.read())

    conn.commit()
    print("Banco de dados configurado.")

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()
