from qmtl.brokerage import IBKRFeeModel


def test_ibkr_fee_applies_tiers_and_minimum():
    fee = IBKRFeeModel(tiers=[(300000, 0.0035)], minimum=1.0, exchange_fees=0.0)
    # Small order -> minimum
    assert fee.calculate(order=type('O', (), {'quantity': 10})(), fill_price=100.0) == 1.0
    # Medium order inside first tier
    assert fee.calculate(order=type('O', (), {'quantity': 1000})(), fill_price=100.0) == 1000 * 0.0035
    # Beyond first tier uses last_rate 0.0020
    assert fee.calculate(order=type('O', (), {'quantity': 300500})(), fill_price=100.0) == 300000 * 0.0035 + 500 * 0.0020

