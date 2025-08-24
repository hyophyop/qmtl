# Dynamic Execution Diffusion-Contraction Theory

Execution diffusion-contraction evaluates how executed prices cluster or disperse and the expected jump from latent depth.

## Concentration scores

```
entropy, hhi, fano = concentration_scores(exec_prices_ticks, exec_sizes, bins)
```

Histogram binning of executed prices yields entropy, Herfindahl-Hirschman Index and a Fano-based dispersion ratio.

## Hazard probability

A logistic model maps standardized features ``x`` and coefficients ``eta`` to a diffusion-contraction hazard:

```
hazard = 1 / (1 + exp(-(eta0 + sum(eta_i * x_i))))
```

## Expected jump and alpha

Given gap widths and cumulative depth, the expected jump size is accumulated with parameter ``zeta``. The side-specific signal is

```
edch = hazard * expected_jump
```
