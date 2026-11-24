"""Carrega a base limpa de saida/ no banco criado por setup_db.py.

Uso: python scripts/load_data.py  (rode clean_data.py antes)

Tudo em uma transação: ou entra a base inteira, ou nada. Só carrega em tabelas
vazias, para rodar duas vezes não duplicar pagamentos.
apresentado_em, prazo, situacao e observacao ficam só no CSV: o schema não tem essas colunas.
"""
import csv
from pathlib import Path

import psycopg2

SAIDA = Path(__file__).resolve().parent.parent / "saida"


def ler(nome):
    with (SAIDA / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    precatorios, pagamentos = ler("precatorios.csv"), ler("pagamentos.csv")
    conn = psycopg2.connect(host="localhost", port=5432, dbname="dados", user="postgres", password="postgres")
    try:
        # "with conn" faz commit no fim, ou rollback se qualquer linha falhar
        with conn, conn.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM precatorio) OR EXISTS (SELECT 1 FROM pagamento)")
            if cursor.fetchone()[0]:
                raise SystemExit("O banco já tem dados; nada foi carregado.")

            ids = {}
            for p in precatorios:
                cursor.execute(
                    "INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (p["numero_processo"], p["ente_devedor"], p["valor_face"] or None),
                )
                ids[p["numero_processo"]] = cursor.fetchone()[0]

            for p in pagamentos:
                cursor.execute(
                    "INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (ids[p["numero_processo"]], p["evento_id"], p["tipo"], p["valor"], p["pago_em"]),
                )
    finally:
        conn.close()
    print(f"Carregados {len(precatorios)} precatórios e {len(pagamentos)} pagamentos.")


if __name__ == "__main__":
    main()
