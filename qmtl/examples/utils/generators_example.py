from qmtl.runtime.generators import GarchInput


def main() -> None:
    stream = GarchInput(interval="60s", period=5, seed=42)
    data = stream.generate(10)
    for ts, payload in data:
        print(ts, payload)


if __name__ == "__main__":
    main()
