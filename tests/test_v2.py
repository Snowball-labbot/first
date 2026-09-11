import unittest
import numpy as np
from src.q12 import B,optimize_day
from src.q34 import revise_plan
from src.v2_model import remove_cycles,solve,corrected_load,risk_buffers


class V2Tests(unittest.TestCase):
    def test_cycle_elimination_preserves_storage_balance_and_limits(self):
        c=np.array([500.,100.,0.]);d=np.array([400.,300.,10.]);w=np.array([0.,7.,8.])
        cc,dd,ww=remove_cycles(c,d,w)
        np.testing.assert_allclose(B.eta_c*c-d/B.eta_d,B.eta_c*cc-dd/B.eta_d,atol=1e-10)
        np.testing.assert_allclose(c-d+w,cc-dd+ww,atol=1e-10)
        self.assertFalse(((cc>1e-8)&(dd>1e-8)).any())
        self.assertTrue((cc<=c+1e-8).all() and (dd<=d+1e-8).all())

    def test_lp_equals_milp_random_solar_surplus_and_revisions(self):
        rng=np.random.default_rng(72)
        for trial in range(8):
            l=rng.uniform(0,800,12);pv=rng.uniform(0,1600,12);p=rng.uniform(.1,2,12)
            a,ma=solve(l,pv,p,6000,equal=True)
            b,mb=optimize_day(l,pv,p,6000,(6000,'equal'))
            self.assertAlmostEqual(ma['objective'],mb['cost'],places=5)
            for refund in [True,False]:
                old=rng.uniform(0,900,12)
                a,ma=solve(l,pv,p,6000,old=old,refund=refund)
                b,mb=revise_plan(l,pv,p,6000,old,refund)
                self.assertAlmostEqual(ma['objective'],mb['objective'],places=5)

    def test_load_update_does_not_see_current_slot_or_future(self):
        values=np.arange(12*144,dtype=float).reshape(12,144)
        pred={'load':values*.9};data={'load':values.copy()}
        a=corrected_load(data,pred,1.)
        data['load'][10,72:]=1e8;data['load'][11:]=1e8
        b=corrected_load(data,pred,1.)
        np.testing.assert_array_equal(a[:10],b[:10])
        np.testing.assert_array_equal(a[10,:3],b[10,:3])

    def test_buffers_do_not_use_current_day(self):
        rng=np.random.default_rng(22);load=rng.random((12,144))*100
        data={'load':load.copy(),'pv':load*.1};lp=np.repeat(load[:,None,:]*.9,4,axis=1);pv=lp*.1
        a=risk_buffers(data,lp,pv,.7)
        data['load'][10:]*=100
        b=risk_buffers(data,lp,pv,.7)
        np.testing.assert_array_equal(a[:11],b[:11])


if __name__=='__main__':unittest.main()
