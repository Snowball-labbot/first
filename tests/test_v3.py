import unittest
import numpy as np
from src.v3_model import solve

class SettlementTests(unittest.TestCase):
    def test_down_payment(self):
        f,m=solve([80],[0],[1],6000,6000,old=[100],equal=True)
        self.assertAlmostEqual(100+m['objective'],90)
        self.assertAlmostEqual(f.plan_kwh.iloc[0],80)
    def test_up_payment(self):
        f,m=solve([120],[0],[1],6000,6000,old=[100],equal=True)
        self.assertAlmostEqual(100+m['objective'],130)
    def test_reversal_final_contract(self):
        # Intermediate 100 -> 80 -> 100 creates no final deviation.
        original=100;last=100;p=1
        bill=p*min(original,last)+.5*p*max(original-last,0)+1.5*p*max(last-original,0)
        self.assertEqual(bill,100)
        _,m=solve([100],[0],[1],6000,6000,old=[original],equal=True)
        self.assertAlmostEqual(original+m['objective'],bill)

if __name__=='__main__':unittest.main()
