from qmtl.generators.all_alpha import all_alpha_generator_node

def test_all_alpha_generator_keys():
    data = all_alpha_generator_node()
    assert set(data.keys()) == {"apb", "llrti", "non_linear", "order_book", "qle", "resiliency"}
    assert set(data["apb"].keys()) == {"price", "volume", "volume_hat", "volume_std"}
    assert set(data["llrti"].keys()) == {"depth_changes", "price_change", "delta_t", "delta"}
    assert set(data["non_linear"].keys()) == {"impact", "volatility", "obi_derivative"}
    assert set(data["order_book"].keys()) == {"hazard_ask", "hazard_bid", "g_ask", "g_bid", "pi", "cost"}
    assert set(data["qle"].keys()) == {"alphas", "delta_t", "tau", "sigma", "threshold"}
    assert set(data["resiliency"].keys()) == {"volume", "avg_volume", "depth", "volatility", "obi_derivative", "beta", "gamma"}


def test_all_alpha_generator_history_window():
    for _ in range(10):
        data = all_alpha_generator_node()
    assert len(data["llrti"]["depth_changes"]) == 3
    assert len(data["qle"]["alphas"]) == 3
