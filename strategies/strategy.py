try:
    from dags.my_strategy import MyStrategy
except ModuleNotFoundError:  # pragma: no cover
    from strategies.dags.my_strategy import MyStrategy


if __name__ == "__main__":
    MyStrategy().run()
