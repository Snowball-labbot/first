import unittest
import numpy as np
from scipy.optimize import linprog
from src.v5b_value import deterministic,recourse_values,execute_value
from src.v3_model import solve
from src.q12 import B


class ContinuousValueTests(unittest.TestCase):
    def test_real_time_price_causality_and_common_scaling(self):
        from src.v5b_rolling import execute_prefix
        plan=np.zeros(3);load=np.array([200.,800.,200.]);pv=np.zeros(3);p=np.array([.1,1.,.3]);paths=load[None,:]
        a=execute_prefix(plan,load,pv,1800.,p,p,paths,1)
        changed=p.copy();changed[1:]=99999
        b=execute_prefix(plan,load,pv,1800.,changed,p,paths,1)
        c=execute_prefix(plan,load,pv,1800.,2*p,2*p,paths,1)
        self.assertAlmostEqual(a.discharge_kwh.iloc[0],b.discharge_kwh.iloc[0],places=8)
        self.assertAlmostEqual(a.discharge_kwh.iloc[0],c.discharge_kwh.iloc[0],places=8)

    def test_dp_matches_lp_without_storage_grid(self):
        rng=np.random.default_rng(23)
        for n in [2,6,24,144]:
            l=rng.uniform(10,800,n);v=rng.uniform(0,900,n);p=rng.uniform(.01,2,n)
            f,value=deterministic(l,v,p)
            _,lp=solve(l,v,p,6000,equal=True)
            self.assertAlmostEqual(float(value[0].at(6000)),lp['objective'],places=6)
            self.assertTrue((np.diff(value[0].slopes)>=-1e-7).all())

    def test_recourse_value_against_direct_emergency_lp(self):
        net=np.array([200.,800.,200.]);price=np.array([.1,1.,.3]);initial=1800.
        values=recourse_values(net,price,0.)
        # Discharges are bus energy; cumulative inventory limits, no charging.
        c=-5*price;A=np.tril(np.ones((3,3)))/B.eta_d
        lp=linprog(c,A_ub=A,b_ub=np.full(3,initial-B.minimum),bounds=[(0,min(x,B.limit)) for x in net],method='highs')
        expected=float(5*price@net+lp.fun)
        self.assertAlmostEqual(float(values[0].at(initial)),expected,places=6)

    def test_current_action_ignores_unobserved_actual_future(self):
        plan=np.zeros(3);load=np.array([200.,800.,200.]);pv=np.zeros(3);p=np.array([.1,1.,.3]);paths=load[None,:]
        f=execute_value(plan,load,pv,1800.,p,paths,0.)
        altered=load.copy();altered[1:]=99999
        g=execute_value(plan,altered,pv,1800.,p,paths,0.)
        self.assertAlmostEqual(f.discharge_kwh.iloc[0],g.discharge_kwh.iloc[0],places=8)
        self.assertAlmostEqual(f.discharge_kwh.iloc[0],0.,places=8)
        self.assertGreater(f.emergency_kwh.iloc[0],0.)

if __name__=='__main__':unittest.main()
