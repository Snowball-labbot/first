import unittest
import numpy as np
import pandas as pd
from src.q12 import B, audit_trace, execute_day, features, optimize_day, interval_label


class PhysicalTests(unittest.TestCase):
    def test_emergency_only_after_feasible_discharge(self):
        f = execute_day([0,0],[1000,1000],[0,0],B.minimum+100,[1,1])
        self.assertAlmostEqual(f.discharge_kwh.iloc[0],90)
        self.assertAlmostEqual(f.emergency_kwh.sum(),1910)
        self.assertAlmostEqual(f.soc_end_kwh.iloc[-1],B.minimum)

    def test_surplus_capacity_and_energy_conservation(self):
        f = execute_day([0],[0],[1000],B.maximum-90,[1])
        self.assertAlmostEqual(f.charge_kwh.iloc[0],100)
        self.assertAlmostEqual(f.spill_kwh.iloc[0],900)
        self.assertAlmostEqual(f.soc_end_kwh.iloc[0],B.maximum)

    def test_causal_controller_prefix(self):
        a = execute_day([100]*4,[200,300,400,500],[0]*4,6000,[1]*4)
        b = execute_day([100]*4,[200,300,9000,1],[0]*4,6000,[1]*4)
        pd.testing.assert_frame_equal(a.iloc[:2],b.iloc[:2])

    def test_features_ignore_same_day_and_future(self):
        a=np.arange(20*144).reshape(20,144).astype(float)
        dates=pd.date_range('2025-01-01',periods=20)
        x=features(a,10,dates)
        a[10:]+=99999
        np.testing.assert_array_equal(x,features(a,10,dates))

    def test_optimum_against_known_small_arbitrage(self):
        f,m=optimize_day(np.array([0,100.]),np.zeros(2),np.array([1.,3.]),1200,(1200,'equal'))
        self.assertAlmostEqual(f.plan_kwh.iloc[0],100/0.81,places=5)
        self.assertAlmostEqual(m['cost'],100/0.81,places=5)

    def test_audit_rejects_broken_balance(self):
        f=execute_day([100],[100],[0],6000,[1])
        f.loc[0,'plan_kwh']=101
        with self.assertRaises(AssertionError): audit_trace(f)

    def test_interval_endpoints(self):
        self.assertEqual(interval_label(0),'00:00-00:10')
        self.assertEqual(interval_label(143),'23:50-24:00')


if __name__ == '__main__': unittest.main()
