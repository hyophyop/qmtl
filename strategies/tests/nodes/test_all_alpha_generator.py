from strategies.nodes.generators import all_alpha_generator_node


def test_all_alpha_generator_structure():
    data = all_alpha_generator_node()
    assert set(data.keys()) == {"apb", "llrti", "non_linear", "order_book", "qle", "resiliency"}
    assert "price" in data["apb"]
    assert "hazard_ask" in data["order_book"]
