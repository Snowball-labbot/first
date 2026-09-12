import unittest
import numpy as np
from src.q12 import B,execute_day
from src.v3_model import solve
from src.v5_model import adaptive_load


class V5PitfallTests(unittest.TestCase):
    def test_surplus_is_permitted_and_plan_is_fully_billed(self):
        f=execute_day([1000.],[100.],[0.],B.maximum,[2.])
        self.assertAlmostEqual(float(f.spill_kwh.iloc[0]),900.)
        self.assertAlmostEqual(float((f.price*(f.plan_kwh+5*f.emergency_kwh)).sum()),2000.)
        self.assertAlmostEqual(B.limit,5000/6)

    def test_equal_balance_with_curtailment_accepts_excess_pv(self):
        f,m=solve([100.],[1000.],[1.],B.maximum,terminal=B.maximum,equal=True)
        self.assertAlmostEqual(m['objective'],0.)
        self.assertGreaterEqual(float(f.spill_kwh.iloc[0]),900.-1e-7)

    def test_same_day_future_does_not_change_released_load_forecasts(self):
        rng=np.random.default_rng(5);pred=np.full((35,144),500.)
        actual=pred+rng.normal(0,30,pred.shape)
        first,_=adaptive_load({'load':actual},pred)
        altered=actual.copy();altered[22,72:]+=1e6;altered[23:]+=1e6
        second,_=adaptive_load({'load':altered},pred)
        np.testing.assert_array_equal(first[:22],second[:22])
        np.testing.assert_array_equal(first[22,:3],second[22,:3])

if __name__=='__main__':unittest.main()
