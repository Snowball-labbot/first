import unittest
import numpy as np
import torch
from src.q4_forecast import features_at,PriceGRU


class PriceTests(unittest.TestCase):
    def test_inputs_ignore_origin_and_future(self):
        prices=np.arange(3000,dtype=float);before=features_at(prices,1600)
        prices[1600:]=-999
        np.testing.assert_array_equal(before,features_at(prices,1600))
        self.assertEqual(before[0,0],1456);self.assertEqual(before[-1,0],1599)
        self.assertEqual(before[0,1],592)

    def test_gru_direct_shape_and_gradients(self):
        torch.manual_seed(17);m=PriceGRU();x=torch.randn(3,144,6)
        y=m(x);self.assertEqual(tuple(y.shape),(3,144));self.assertTrue(torch.isfinite(y).all())
        loss=(y-torch.randn_like(y)).square().mean();loss.backward()
        self.assertTrue(torch.isfinite(m.head.weight.grad).all())
        self.assertGreater(float(m.head.weight.grad.abs().sum()),0)


if __name__=='__main__':unittest.main()
