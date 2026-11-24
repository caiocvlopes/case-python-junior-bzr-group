"""Testes das regras mais arriscadas. Uso: python -m unittest discover -s scripts"""
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import clean_data as c


def evento(valor, atualizado_em="2025-01-01T10:00:00-03:00"):
    return {"evento_id": "ev-1", "valor": valor, "atualizado_em": atualizado_em}


class Prazo(unittest.TestCase):
    def prazo(self, texto):
        return c.prazo_pagamento(c.data_apresentacao(texto))

    def test_2_de_abril_esta_dentro(self):
        self.assertEqual(self.prazo("2025-04-02"), date(2026, 12, 31))
        self.assertEqual(self.prazo("2025-04-03"), date(2027, 12, 31))

    def test_conta_pela_data_de_brasilia(self):
        self.assertEqual(self.prazo("2025-04-03T01:00:00Z"), date(2026, 12, 31))
        self.assertEqual(self.prazo("2025-04-02T23:30:00-03:00"), date(2026, 12, 31))


class Valor(unittest.TestCase):
    def test_formato_brasileiro(self):
        self.assertEqual(c.parse_valor("2.500,50"), Decimal("2500.50"))

    def test_ambiguo_ou_ausente_nao_e_adivinhado(self):
        for bruto in (None, "", "2.500", "2,500.50", Decimal("1.005")):
            self.assertIsNone(c.parse_valor(bruto), bruto)


class Versoes(unittest.TestCase):
    def vigentes(self, *registros):
        return [r["valor"] for _, r in c.versoes_vigentes(list(registros), c.Relatorio())]

    def test_vale_a_mais_recente_mesmo_fora_de_ordem(self):
        novo = evento(20, "2025-01-02T10:00:00-03:00")
        self.assertEqual(self.vigentes(novo, evento(10)), [20])

    def test_copia_identica_conta_uma_vez(self):
        self.assertEqual(self.vigentes(evento(10), evento(10)), [10])

    def test_empate_com_conteudo_diferente_fica_de_fora(self):
        self.assertEqual(self.vigentes(evento(10), evento(20)), [])


class BaseCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = c.RAIZ / "dados"
        cls.originais = {p.name: p.read_bytes() for p in cls.dados.iterdir()}
        cls.tmp = tempfile.TemporaryDirectory()
        cls.precatorios, cls.pagamentos, _ = c.executar(cls.dados, cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_totais_pagos(self):
        totais = {p["processo_cnj"][:7]: p["total_pago"] for p in self.precatorios.values()}
        esperado = {"0012345": "18000.50", "0023456": "9200", "0034567": "0",
                    "0045678": "3000", "0056789": "0", "0067890": "4000"}
        self.assertEqual(totais, {k: Decimal(v) for k, v in esperado.items()})

    def test_rodar_de_novo_nao_muda_o_resultado(self):
        antes = {p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir()}
        c.executar(self.dados, self.tmp.name)
        self.assertEqual(antes, {p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir()})

    def test_originais_intactos(self):
        self.assertEqual(self.originais, {p.name: p.read_bytes() for p in self.dados.iterdir()})


if __name__ == "__main__":
    unittest.main()
