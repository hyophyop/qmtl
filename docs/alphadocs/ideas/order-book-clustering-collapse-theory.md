# Order Book Clustering Collapse Theory

Order book clustering collapse tracks the risk of densely packed orders disintegrating into sparse liquidity.

## Hazard probability

Features $\{C,\text{Cliff},\text{Gap},\text{CH},\text{RL},\text{Shield},\text{QDT\_inv}\}$ feed a logistic hazard model. Feature ``C`` uses a softplus transform and ``Shield`` enters negatively.

## Direction gating and cost

Direction gating supplies a side-aware signal conditioned on imbalance, while execution cost is reused from the generic hazard utilities. Together they describe the likelihood and cost of a clustering collapse.
