import unittest
import numpy as np
from src.q34 import revise_plan, historical_buffers
from src.q12 import B


class ExtendedTests(unittest.TestCase):
    def test_unused_original_plan_cancels_with_half_recovery(self):
        f,m=revise_plan(np.zeros(2),np.zeros(2),np.ones(2),6000,np.ones(2)*10)
        np.testing.assert_allclose(f.plan_kwh,0,atol=1e-6)
        self.assertAlmostEqual(m['objective'],-10)

    def test_no_refund_does_not_pay_to_cancel(self):
        f,m=revise_plan(np.zeros(2),np.zeros(2),np.ones(2),6000,np.ones(2)*10,refund=False)
        np.testing.assert_allclose(f.plan_kwh,10,atol=1e-6)
        self.assertAlmostEqual(m['objective'],0)

    def test_increase_price_and_initial_soc(self):
        f,m=revise_plan(np.ones(1)*100,np.zeros(1),np.ones(1),6000,np.zeros(1))
        self.assertAlmostEqual(f.plan_kwh.iloc[0],100)
        self.assertAlmostEqual(m['objective'],150)
        self.assertAlmostEqual(f.soc_end_kwh.iloc[-1],6000)

    def test_version_reserve_does_not_read_today(self):
        data={'load':np.ones((9,144))*100,'pv':np.ones((9,144))*10,
            'pv_issued':np.ones((9,4,144))*20}
        pred={'load':np.ones((9,144))*100}
        a=historical_buffers(data,pred,.7)
        data['load'][8:]*=10;data['pv'][8:]*=3;data['pv_issued'][8:]*=2
        b=historical_buffers(data,pred,.7)
        np.testing.assert_allclose(a[:9],b[:9],equal_nan=True)


if __name__=='__main__':unittest.main()
