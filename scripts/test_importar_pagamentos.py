"""Testes da importação em um banco temporário. São pulados sem psycopg2 ou sem o Postgres no ar."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

try:
    import psycopg2

    import importar_pagamentos as imp
except ImportError:
    psycopg2 = None

RAIZ = Path(__file__).resolve().parent.parent
BANCO = "teste_importacao"
PROCESSO = "00123451020198260053"
PROCESSOS = [PROCESSO, "00234562120208260053", "00345673220188260405",
             "00456784320215020011", "00567895420174036100", "00678906520168260053"]


def conectar(banco):
    return psycopg2.connect(host="localhost", port=5432, dbname=banco, user="postgres",
                            password="postgres", connect_timeout=2)


def administrar(*comandos):
    conn = conectar("postgres")
    conn.autocommit = True
    try:
        for comando in comandos:
            conn.cursor().execute(comando)
    finally:
        conn.close()


def evento(valor, versao=1, evento_id="ev-t"):
    return {"evento_id": evento_id, "processo": PROCESSO, "valor": valor, "data_pagamento": "2025-03-10",
            "tipo": "pagamento", "atualizado_em": f"2025-03-1{versao}T10:00:00-03:00"}


@unittest.skipIf(psycopg2 is None, "psycopg2 não instalado")
class Importacao(unittest.TestCase):
    def setUp(self):
        try:
            administrar(f"DROP DATABASE IF EXISTS {BANCO}", f"CREATE DATABASE {BANCO}")
        except psycopg2.OperationalError:
            self.skipTest("Postgres fora do ar")
        self.conn = conectar(BANCO)
        self.pasta = tempfile.TemporaryDirectory()
        with self.conn, self.conn.cursor() as cur:
            cur.execute((RAIZ / "schema.sql").read_text(encoding="utf-8"))
        self.conn.autocommit = True
        self.conn.cursor().execute((RAIZ / "sql" / "prevencao.sql").read_text(encoding="utf-8"))
        self.conn.autocommit = False
        with self.conn, self.conn.cursor() as cur:
            cur.execute("INSERT INTO ente VALUES ('União')")
            for processo in PROCESSOS:
                cur.execute("INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) "
                            "VALUES (%s, 'União', 100000)", (processo,))

    def tearDown(self):
        self.conn.close()
        self.pasta.cleanup()
        administrar(f"DROP DATABASE {BANCO}")

    def importar(self, conteudo):
        caminho = Path(self.pasta.name) / "pagamentos.json"
        caminho.write_text(json.dumps(conteudo), encoding="utf-8")
        return imp.importar(self.conn, caminho)

    def consultar(self, sql):
        with self.conn, self.conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]

    def total(self):
        return self.consultar("SELECT COALESCE(SUM(total), 0) FROM total_pago")

    def pendentes(self):
        return self.consultar("SELECT count(*) FROM pendencia")

    def test_arquivo_do_case_rodado_duas_vezes(self):
        original = RAIZ / "dados" / "pagamentos.json"
        for _ in range(2):
            imp.importar(self.conn, original)
            self.assertEqual(self.total(), Decimal("34200.50"))
            self.assertEqual(self.pendentes(), 3)  # ev-004, ev-009, ev-010

    def test_versao_antiga_que_chega_depois_nao_substitui(self):
        self.importar([evento(20, versao=2)])
        self.importar([evento(10, versao=1)])
        self.assertEqual(self.total(), 20)

    def test_versao_vigente_invalida_sai_do_total_e_nao_volta(self):
        self.importar([evento(10, versao=1)])
        self.importar([evento(None, versao=2)])
        self.importar([evento(10, versao=1)])
        self.assertEqual((self.total(), self.pendentes()), (0, 1))
        self.importar([evento(30, versao=3)])
        self.assertEqual((self.total(), self.pendentes()), (30, 0))

    def test_empate_com_conteudo_diferente_vira_pendencia(self):
        self.importar([evento(10)])
        self.importar([evento(20)])
        self.assertEqual((self.total(), self.pendentes()), (0, 1))

    def test_registro_ruim_nao_derruba_os_outros(self):
        self.importar([evento("abc", evento_id="ruim"), evento(10)])
        self.assertEqual((self.total(), self.pendentes()), (10, 1))

    def test_arquivo_fora_do_formato_nao_grava_nada(self):
        with self.assertRaises(imp.ArquivoInvalido):
            self.importar([evento(10), {"evento_id": "sem-campos"}])
        self.assertEqual(self.consultar("SELECT count(*) FROM importacao"), 0)


if __name__ == "__main__":
    unittest.main()
