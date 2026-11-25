"""Aplica sql/prevencao.sql no banco criado por setup_db.py.

Uso: python scripts/aplicar_prevencao.py [--banco NOME]

A migração é uma transação só: se falhar, o banco fica como estava.
Rode depois de load_data.py, que foi feito para o schema anterior à migração.
"""
import argparse
from pathlib import Path

import psycopg2

SQL = Path(__file__).resolve().parent.parent / "sql" / "prevencao.sql"


def main():
    args = argparse.ArgumentParser(description="Aplica a migração de prevenção.")
    args.add_argument("--banco", default="dados")
    banco = args.parse_args().banco

    conn = psycopg2.connect(host="localhost", port=5432, dbname=banco, user="postgres", password="postgres")
    # o próprio arquivo SQL tem BEGIN e COMMIT
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('precatorio'), to_regclass('pagamento'), to_regclass('evento_recebido')")
            precatorio, pagamento, evento_recebido = cursor.fetchone()
            if not (precatorio and pagamento):
                raise SystemExit("Schema não encontrado; rode setup_db.py antes.")
            if evento_recebido:
                raise SystemExit("A prevenção já foi aplicada; nada foi alterado.")
            try:
                cursor.execute(SQL.read_text(encoding="utf-8"))
            except psycopg2.Error as erro:
                raise SystemExit(f"Migração falhou; nada foi alterado.\n{erro}")
    finally:
        # fechar a conexão descarta uma transação que ficou aberta por erro
        conn.close()
    print(f"Prevenção aplicada no banco {banco}.")


if __name__ == "__main__":
    main()
