import math
import unittest

from iqbot import indicadores as ind
from iqbot.analise import analisar, backtest


def _velas(precos):
    velas, anterior = [], precos[0]
    for i, p in enumerate(precos):
        velas.append({"from": i * 60, "open": anterior, "close": p,
                      "max": max(anterior, p) + 0.0001, "min": min(anterior, p) - 0.0001})
        anterior = p
    return velas


class TestIndicadores(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(ind.sma([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])

    def test_rsi_so_alta_e_100(self):
        self.assertEqual(ind.rsi([float(i) for i in range(30)], 14)[-1], 100.0)

    def test_ema_constante(self):
        self.assertAlmostEqual(ind.ema([5.0] * 30, 9)[-1], 5.0)


class TestAnalise(unittest.TestCase):
    def test_queda_forte_sobrevendido(self):
        r = analisar(_velas([1.10 - i * 0.001 for i in range(60)]))
        self.assertLess(r["rsi14"], 30)
        self.assertIn(r["sinal"], ("CALL", "NEUTRO", "PUT"))

    def test_lateral_neutro(self):
        r = analisar(_velas([1.10 + 0.0005 * math.sin(i / 2) for i in range(80)]))
        self.assertIn("motivos", r)

    def test_poucas_velas(self):
        with self.assertRaises(ValueError):
            analisar(_velas([1.0] * 10))

    def test_backtest(self):
        precos = [1.10 + 0.002 * math.sin(i / 5) + 0.0003 * math.sin(i * 1.7) for i in range(300)]
        r = backtest(_velas(precos))
        self.assertEqual(r["taxa_minima_para_lucrar"], 55.6)
        g = r["geral"]
        self.assertEqual(g["operacoes"], sum(v["operacoes"] for v in r["por_forca_do_sinal"].values()))


if __name__ == "__main__":
    unittest.main()
