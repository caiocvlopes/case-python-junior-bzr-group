"""Lê os arquivos de dados/ como vieram e gera uma base limpa e um relatório em saida/.

Uso: python scripts/clean_data.py [--dados PASTA] [--saida PASTA]

Premissas (a confirmar com o tribunal, ver DIAGNOSTICO.md):
- vale a versão de atualizado_em mais recente de cada evento;
- estorno subtrai do total pago;
- "2.500,50" e "10/04/2025" estão no formato brasileiro;
- o prazo conta pela data de Brasília;
- onde tribunal.csv e hub.csv divergem, fica o valor do tribunal, marcado como dúvida.
"""
import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Offset fixo: o Brasil não tem horário de verão desde 2019.
BRASILIA = timezone(timedelta(hours=-3))
CORRIGIDO, DESCARTADO, DUVIDA = "Corrigido", "Descartado", "Em dúvida"


class Relatorio:
    def __init__(self):
        self.itens = []

    def add(self, categoria, onde, motivo, processo=None):
        self.itens.append((categoria, onde, motivo, processo))

    def duvidas_do_processo(self, processo):
        return [f"{onde}: {motivo}" for cat, onde, motivo, p in self.itens if cat == DUVIDA and p == processo]

    def markdown(self):
        linhas = ["# Relatório da limpeza", "", "Itens `ev-…` são eventos do pagamentos.json."]
        for categoria in (CORRIGIDO, DESCARTADO, DUVIDA):
            itens = [i for i in self.itens if i[0] == categoria]
            linhas += ["", f"## {categoria} ({len(itens)})", ""]
            linhas += [f"- **{onde}**: {motivo}" for _, onde, motivo, _ in itens]
        return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- conversões

def normalizar_processo(texto):
    """CNJ formatado ou só dígitos -> 20 dígitos. None se não for um processo."""
    texto = str(texto or "").strip()
    if not re.fullmatch(r"\d{20}|\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", texto):
        return None
    return re.sub(r"\D", "", texto)


def formatar_cnj(p):
    return f"{p[:7]}-{p[7:9]}.{p[9:13]}.{p[13]}.{p[14:16]}.{p[16:]}"


def parse_valor(bruto):
    """Devolve Decimal ou None. Texto só é aceito se o formato não for ambíguo."""
    if isinstance(bruto, bool) or bruto is None:
        return None
    if isinstance(bruto, (int, Decimal)):
        valor = Decimal(bruto)
    elif isinstance(bruto, str):
        texto = bruto.strip()
        if re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+),\d{1,2}", texto):  # 2.500,50
            texto = texto.replace(".", "").replace(",", ".")
        elif not re.fullmatch(r"-?\d+(\.\d{1,2})?", texto):  # 2500.50
            return None
        valor = Decimal(texto)
    else:
        return None
    # NUMERIC(15,2): mais de 2 casas seria arredondado em silêncio pelo banco
    if not valor.is_finite() or valor != valor.quantize(Decimal("0.01")):
        return None
    return valor


def parse_data(texto):
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except (TypeError, ValueError):
            pass
    return None


def parse_momento(texto):
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=BRASILIA)


def data_apresentacao(texto):
    """Data de Brasília de uma data pura ou data-hora com fuso."""
    if isinstance(texto, str) and len(texto) == 10:
        return parse_data(texto)
    momento = parse_momento(texto)
    return momento.astimezone(BRASILIA).date() if momento else None


def prazo_pagamento(apresentado):
    anos = 1 if apresentado <= date(apresentado.year, 4, 2) else 2
    return date(apresentado.year + anos, 12, 31)


def normalizar_ente(nome):
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


# ---------------------------------------------------------------- leitura

def ler_csv(caminho, rel):
    bruto = caminho.read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252")
        rel.add(CORRIGIDO, caminho.name, "não é UTF-8; lido como Windows-1252")
    separador = ";" if ";" in texto.split("\n", 1)[0] else ","
    if caminho.name == "tribunal.csv" and separador == ";":
        rel.add(CORRIGIDO, caminho.name, "separador `;` em vez de vírgula")
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador))


def ler_precatorios_csv(caminho, col_processo, col_ente, rel):
    registros = {}
    for linha, r in enumerate(ler_csv(caminho, rel), start=2):
        onde = f"{caminho.name} linha {linha}"
        processo = normalizar_processo(r[col_processo])
        valor = parse_valor(r["valor_face"])
        if not processo:
            rel.add(DESCARTADO, onde, f"processo inválido: {r[col_processo]!r}")
            continue
        if processo in registros:
            rel.add(DUVIDA, onde, "processo repetido; mantida a primeira linha", processo)
            continue
        if r[col_processo] != formatar_cnj(processo):
            rel.add(CORRIGIDO, onde, f"processo {r[col_processo]} normalizado", processo)
        if valor is None or valor <= 0:
            rel.add(DUVIDA, onde, f"valor_face inválido: {r['valor_face']!r}", processo)
            valor = None
        elif "," in r["valor_face"]:
            rel.add(CORRIGIDO, onde, f"valor_face {r['valor_face']} convertido para {valor}", processo)
        registros[processo] = {**r, "ente": r[col_ente].strip(), "valor": valor, "onde": onde}
    return registros


# ---------------------------------------------------------------- regras

def limpar_precatorios(pasta, rel):
    tribunal = ler_precatorios_csv(pasta / "tribunal.csv", "numero_processo", "ente_devedor", rel)
    hub = ler_precatorios_csv(pasta / "hub.csv", "processo", "ente", rel)
    apresentacoes = {}
    for i, r in enumerate(json.loads((pasta / "apresentacoes.json").read_text(encoding="utf-8-sig")), 1):
        processo = normalizar_processo(r.get("processo"))
        if not processo:
            rel.add(DESCARTADO, f"apresentacoes.json registro {i}", "processo inválido")
        elif processo in apresentacoes and apresentacoes[processo] != r.get("apresentado_em"):
            rel.add(DUVIDA, f"apresentacoes.json registro {i}", "duas datas de apresentação", processo)
        else:
            apresentacoes[processo] = r.get("apresentado_em")

    for processo in sorted(set(apresentacoes) - set(tribunal) - set(hub)):
        rel.add(DUVIDA, formatar_cnj(processo), "só tem data de apresentação; fora da base", processo)

    base = {}
    for processo in sorted(set(tribunal) | set(hub)):
        cnj = formatar_cnj(processo)
        t, h = tribunal.get(processo), hub.get(processo)
        fonte = t or h
        if not h:
            rel.add(CORRIGIDO, cnj, "ausente no hub.csv; incluído a partir do tribunal.csv", processo)
        elif not t:
            rel.add(DUVIDA, cnj, "só existe no hub.csv; mantido com os dados do hub", processo)
        else:
            if t["valor"] != h["valor"]:
                rel.add(DUVIDA, cnj, f"valor_face {t['valor']} no tribunal e {h['valor']} no hub; "
                        "usado o do tribunal", processo)
            if normalizar_ente(t["ente"]) != normalizar_ente(h["ente"]):
                rel.add(DUVIDA, cnj, f"ente '{t['ente']}' no tribunal e '{h['ente']}' no hub; "
                        "usado o do tribunal", processo)
            elif t["ente"] != h["ente"]:
                rel.add(CORRIGIDO, h["onde"], f"ente '{h['ente']}' padronizado para '{t['ente']}'", processo)

        bruto = apresentacoes.get(processo) or (h or {}).get("apresentado_em")
        if h and h["apresentado_em"] != bruto:
            rel.add(DUVIDA, h["onde"], "data de apresentação difere de apresentacoes.json", processo)
        apresentado = data_apresentacao(bruto)
        prazo = prazo_pagamento(apresentado) if apresentado else None
        if not apresentado:
            rel.add(DUVIDA, cnj, f"sem data de apresentação válida ({bruto!r}); sem prazo", processo)
        else:
            if str(apresentado) != bruto[:10]:
                rel.add(DUVIDA, cnj, f"{bruto} é {apresentado} em Brasília; prazo depende do fuso", processo)
            if h and h["prazo_pagamento"] != str(prazo):
                rel.add(CORRIGIDO, h["onde"], f"prazo {h['prazo_pagamento']} recalculado para {prazo}", processo)

        base[processo] = {
            "numero_processo": processo,
            "processo_cnj": cnj,
            "ente_devedor": fonte["ente"],
            "valor_face": fonte["valor"],
            "apresentado_em": apresentado,
            "prazo_pagamento": prazo,
            "total_pago": Decimal("0.00"),
        }
    return base


def versoes_vigentes(registros, rel):
    """Uma versão por evento_id: a de atualizado_em mais recente."""
    grupos = {}
    for i, r in enumerate(registros, 1):
        if not r.get("evento_id"):
            rel.add(DUVIDA, f"pagamentos.json registro {i}", "sem evento_id; fora da base",
                    normalizar_processo(r.get("processo")))
            continue
        grupos.setdefault(r["evento_id"], []).append(r)

    for evento, versoes in grupos.items():
        momentos = [parse_momento(v.get("atualizado_em")) for v in versoes]
        processo = normalizar_processo(versoes[0].get("processo"))
        if None in momentos:
            rel.add(DUVIDA, evento, "atualizado_em inválido; não dá para saber a versão vigente", processo)
            continue
        recente = max(momentos)
        candidatas = [v for v, m in zip(versoes, momentos) if m == recente]
        vigente = candidatas[0]
        if any(v != vigente for v in candidatas):
            rel.add(DUVIDA, evento, "versões diferentes com o mesmo atualizado_em; fora da base", processo)
            continue
        if len(candidatas) > 1:
            rel.add(DESCARTADO, evento, f"{len(candidatas) - 1} cópia(s) idêntica(s)")
        for v, m in zip(versoes, momentos):
            if m < recente:
                rel.add(DESCARTADO, evento, f"versão antiga (valor {v.get('valor')}) substituída pela de "
                        f"{vigente['atualizado_em']} (valor {vigente.get('valor')})")
        yield evento, vigente


def limpar_pagamentos(registros, precatorios, rel):
    pagamentos = []
    # A versão vigente é escolhida antes de validar: se ela for inválida,
    # o evento fica em dúvida em vez de voltar para uma versão antiga.
    for evento, r in versoes_vigentes(registros, rel):
        processo = normalizar_processo(r.get("processo"))
        valor = parse_valor(r.get("valor"))
        pago_em = parse_data(r.get("data_pagamento"))
        tipo = r.get("tipo")

        problemas = []
        if not processo:
            problemas.append(f"processo vazio ou inválido ({r.get('processo')!r})")
        elif processo not in precatorios:
            problemas.append("processo não está na base de precatórios")
        if valor is None:
            problemas.append(f"valor ausente ou ilegível ({r.get('valor')!r})")
        elif valor <= 0:
            problemas.append(f"valor {valor} não é positivo (estorno mal codificado?)")
        if not pago_em:
            problemas.append(f"data inválida ({r.get('data_pagamento')!r})")
        if tipo not in ("pagamento", "estorno"):
            problemas.append(f"tipo desconhecido ({tipo!r})")
        if problemas:
            detalhe = f"valor informado {r.get('valor')}, data {r.get('data_pagamento')}"
            rel.add(DUVIDA, evento, f"fora da base: {'; '.join(problemas)} [{detalhe}]", processo)
            continue

        if r["processo"] != formatar_cnj(processo):
            rel.add(CORRIGIDO, evento, f"processo {r['processo']} normalizado", processo)
        if isinstance(r["valor"], str):
            rel.add(CORRIGIDO, evento, f"valor '{r['valor']}' convertido para {valor}", processo)
        if r["data_pagamento"] != str(pago_em):
            rel.add(CORRIGIDO, evento, f"data '{r['data_pagamento']}' convertida para {pago_em}", processo)

        apresentado = precatorios[processo]["apresentado_em"]
        if apresentado and pago_em < apresentado:
            rel.add(DUVIDA, evento, f"mantido, mas pago em {pago_em}, antes da apresentação "
                    f"({apresentado})", processo)

        pagamentos.append({
            "evento_id": evento,
            "numero_processo": processo,
            "tipo": tipo,
            "valor": valor.quantize(Decimal("0.01")),
            "pago_em": pago_em,
            "atualizado_em": r["atualizado_em"],
        })

    for p in pagamentos:
        precatorios[p["numero_processo"]]["total_pago"] += p["valor"] if p["tipo"] == "pagamento" else -p["valor"]
        if p["tipo"] == "estorno" and not any(
            o["tipo"] == "pagamento" and (o["numero_processo"], o["valor"]) == (p["numero_processo"], p["valor"])
            for o in pagamentos
        ):
            rel.add(DUVIDA, p["evento_id"], "estorno sem pagamento correspondente no arquivo", p["numero_processo"])

    for processo, p in precatorios.items():
        if p["total_pago"] < 0 or (p["valor_face"] is not None and p["total_pago"] > p["valor_face"]):
            rel.add(DUVIDA, p["processo_cnj"], f"total pago {p['total_pago']} negativo ou acima do valor de face",
                    processo)
    return sorted(pagamentos, key=lambda p: p["evento_id"])


# ---------------------------------------------------------------- saída

def gravar_csv(caminho, linhas, colunas):
    with caminho.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)


def executar(pasta_dados, pasta_saida):
    pasta_dados, pasta_saida = Path(pasta_dados), Path(pasta_saida)
    if pasta_saida.resolve() == pasta_dados.resolve():
        raise ValueError("a saída não pode ser a pasta dos arquivos originais")

    rel = Relatorio()
    precatorios = limpar_precatorios(pasta_dados, rel)
    # parse_float=Decimal: dinheiro nunca passa por float
    registros = json.loads((pasta_dados / "pagamentos.json").read_text(encoding="utf-8-sig"), parse_float=Decimal)
    pagamentos = limpar_pagamentos(registros, precatorios, rel)

    for processo, p in precatorios.items():
        duvidas = rel.duvidas_do_processo(processo)
        p["situacao"] = "duvida" if duvidas else "ok"
        p["observacao"] = " | ".join(duvidas)

    pasta_saida.mkdir(parents=True, exist_ok=True)
    gravar_csv(pasta_saida / "precatorios.csv", precatorios.values(),
               ["numero_processo", "processo_cnj", "ente_devedor", "valor_face", "apresentado_em",
                "prazo_pagamento", "total_pago", "situacao", "observacao"])
    gravar_csv(pasta_saida / "pagamentos.csv", pagamentos,
               ["evento_id", "numero_processo", "tipo", "valor", "pago_em", "atualizado_em"])
    (pasta_saida / "relatorio.md").write_text(rel.markdown(), encoding="utf-8")
    return precatorios, pagamentos, rel


def main():
    args = argparse.ArgumentParser(description="Limpeza dos arquivos do tribunal e do hub.")
    args.add_argument("--dados", default=RAIZ / "dados")
    args.add_argument("--saida", default=RAIZ / "saida")
    opcoes = args.parse_args()
    precatorios, pagamentos, rel = executar(opcoes.dados, opcoes.saida)
    print(f"{len(precatorios)} precatórios, {len(pagamentos)} pagamentos, "
          f"{len(rel.itens)} itens no relatório. Saída em {opcoes.saida}")


if __name__ == "__main__":
    main()
