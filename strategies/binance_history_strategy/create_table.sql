CREATE TABLE IF NOT EXISTS binance_prices (
    node_id VARCHAR,
    interval INT,
    ts TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE
);
