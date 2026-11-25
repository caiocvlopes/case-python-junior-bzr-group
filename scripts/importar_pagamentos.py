"""Importa um pagamentos.json no banco já migrado (aplicar_prevencao.py).

Uso: python scripts/importar_pagamentos.py [arquivo.json] [--banco NOME]

- guarda cada registro como veio em evento_recebido;
- decide a versão vigente de cada evento olhando tudo o que já foi recebido;
- grava com upsert, nunca somando: rodar o mesmo arquivo de novo não muda o total;
- registro ruim vira pendência (view pendencia) sem derrubar os outros;
- uma transação por arquivo: se o programa falhar, nada é gravado.
"""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import psycopg2

import clean_data as c

CAMPOS = {"evento_id", "processo", "valor", "data_pagamento", "tipo", "atualizado_em"}
LIMITE_VALOR = Decimal("1e13")  # NUMERIC(15,2)

UPSERT = """
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (evento_id) DO UPDATE SET
    precatorio_id = EXCLUDED.precatorio_id,
    tipo          = EXCLUDED.tipo,
    valor         = EXCLUDED.valor,
    pago_em       = EXCLUDED.pago_em,
    atualizado_em = EXCLUDED.atualizado_em
WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em
"""


class ArquivoInvalido(Exception):
    pass


def _constante_invalida(nome):
    raise ValueError(f"{nome} não é JSON válido")


def ler_arquivo(conteudo):
    """Confere o formato antes de gravar qualquer coisa."""
    try:
        registros = json.loads(conteudo.decode("utf-8-sig"), parse_constant=_constante_invalida)
    except ValueError as erro:
        raise ArquivoInvalido(f"não é um JSON em UTF-8: {erro}")
    if not isinstance(registros, list):
        raise ArquivoInvalido("esperava uma lista de eventos")
    for i, r in enumerate(registros, 1):
        if not isinstance(r, dict) or not CAMPOS <= r.keys():
            raise ArquivoInvalido(f"registro {i} sem os campos {sorted(CAMPOS)}")
    return registros


def marcar_erro(cursor, id_recebido, motivo):
    # a linha pode ter sido resolvida antes e voltar a ser a vigente
    cursor.execute("UPDATE evento_recebido SET erro = %s, resolvido_em = NULL WHERE id = %s", (motivo, id_recebido))


def historico(cursor, evento_id):
    """Tudo o que já chegou deste evento e tem atualizado_em legível."""
    cursor.execute("SELECT id, conteudo::text FROM evento_recebido "
                   "WHERE evento_id = %s AND atualizado_em IS NOT NULL ORDER BY id", (evento_id,))
    return [(i, json.loads(texto, parse_float=Decimal)) for i, texto in cursor.fetchall()]


def precatorios_do_banco(cursor):
    cursor.execute("SELECT id, numero_processo, apresentado_em FROM precatorio")
    return {numero: (id_, apresentado) for id_, numero, apresentado in cursor.fetchall()}


def aplicar_evento(cursor, evento_id, precatorios):
    """Deixa pagamento de acordo com a versão vigente. Devolve (situação, motivo)."""
    recebidos = historico(cursor, evento_id)
    versoes = [r for _, r in recebidos]
    # as mesmas regras da limpeza, aplicadas ao histórico de um evento
    base = {numero: {"apresentado_em": apresentado, "total_pago": Decimal(0),
                     "valor_face": None, "processo_cnj": numero}
            for numero, (_, apresentado) in precatorios.items()}
    rel = c.Relatorio()
    validos = c.limpar_pagamentos(versoes, base, rel)
    recente = max(c.parse_momento(r["atualizado_em"]) for r in versoes)

    # um evento tem no máximo uma pendência aberta: a da avaliação atual
    cursor.execute("UPDATE evento_recebido SET resolvido_em = now() "
                   "WHERE evento_id = %s AND erro IS NOT NULL AND resolvido_em IS NULL", (evento_id,))

    motivo = "; ".join(texto for categoria, _, texto, _ in rel.itens if categoria == c.DUVIDA)
    if validos and validos[0]["valor"] >= LIMITE_VALOR:
        validos, motivo = [], "valor grande demais para o banco"

    if validos:
        p = validos[0]
        cursor.execute(UPSERT, (precatorios[p["numero_processo"]][0], evento_id, p["tipo"], p["valor"],
                                p["pago_em"], c.parse_momento(p["atualizado_em"])))
        return ("aplicado" if cursor.rowcount else "sem mudança"), None

    # versão vigente inválida: sai do total, sem voltar para a versão antiga
    cursor.execute("DELETE FROM pagamento WHERE evento_id = %s AND atualizado_em <= %s", (evento_id, recente))
    id_vigente = [i for i, r in recebidos if c.parse_momento(r["atualizado_em"]) == recente][-1]
    marcar_erro(cursor, id_vigente, motivo)
    return "pendente", motivo


def importar(conn, caminho):
    """Importa um arquivo em uma transação e devolve o resumo."""
    caminho = Path(caminho)
    conteudo = caminho.read_bytes()
    registros = ler_arquivo(conteudo)
    resumo = {"recebidos": len(registros), "aplicado": 0, "sem mudança": 0, "pendente": 0, "pendencias": []}

    with conn, conn.cursor() as cursor:
        # duas importações ao mesmo tempo poderiam decidir a versão com histórico incompleto
        cursor.execute("LOCK TABLE evento_recebido IN EXCLUSIVE MODE")
        cursor.execute("INSERT INTO importacao (arquivo, sha256) VALUES (%s, %s) RETURNING id",
                       (caminho.name, hashlib.sha256(conteudo).hexdigest()))
        importacao_id = cursor.fetchone()[0]

        eventos = {}  # dict para manter a ordem sem repetir
        for r in registros:
            evento_id = r["evento_id"] if isinstance(r["evento_id"], str) and r["evento_id"] else None
            momento = c.parse_momento(r["atualizado_em"])
            bruto = json.dumps(r, ensure_ascii=False)
            motivo = None
            if not evento_id:
                motivo = "sem evento_id"
            elif not momento:
                motivo = "atualizado_em inválido"
            if motivo:
                cursor.execute("UPDATE evento_recebido SET resolvido_em = now() "
                               "WHERE conteudo = %s::jsonb AND erro IS NOT NULL AND resolvido_em IS NULL", (bruto,))
            cursor.execute(
                "INSERT INTO evento_recebido (importacao_id, evento_id, atualizado_em, conteudo, erro) "
                "VALUES (%s, %s, %s, %s, %s)",
                (importacao_id, evento_id, momento, bruto, motivo))
            if motivo:
                resumo["pendente"] += 1
                resumo["pendencias"].append((evento_id, motivo))
            else:
                eventos[evento_id] = None

        precatorios = precatorios_do_banco(cursor)
        for evento_id in eventos:
            situacao, motivo = aplicar_evento(cursor, evento_id, precatorios)
            resumo[situacao] += 1
            if motivo:
                resumo["pendencias"].append((evento_id, motivo))
    return resumo


def main():
    args = argparse.ArgumentParser(description="Importa eventos de pagamento.")
    args.add_argument("arquivo", nargs="?", default=c.RAIZ / "dados" / "pagamentos.json")
    args.add_argument("--banco", default="dados")
    opcoes = args.parse_args()

    conn = psycopg2.connect(host="localhost", port=5432, dbname=opcoes.banco, user="postgres", password="postgres")
    try:
        with conn, conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('evento_recebido')")
            if not cursor.fetchone()[0]:
                raise SystemExit("Banco sem a migração; rode aplicar_prevencao.py antes.")
        try:
            resumo = importar(conn, opcoes.arquivo)
        except ArquivoInvalido as erro:
            raise SystemExit(f"ARQUIVO REJEITADO, nada foi gravado: {erro}")
    finally:
        conn.close()

    print(f"{resumo['recebidos']} registros recebidos. Eventos: {resumo['aplicado']} aplicados, "
          f"{resumo['sem mudança']} sem mudança. Pendências: {resumo['pendente']}.")
    for evento_id, motivo in resumo["pendencias"]:
        print(f"  PENDENTE {evento_id}: {motivo}")


if __name__ == "__main__":
    main()
