# Strategy Templates

QMTL includes several starter strategies that can be copied when running `qmtl init`.
List them with:

```bash
qmtl init --list-templates
```

Available templates are:

- **general** – basic example used by default
- **single_indicator** – single EMA indicator
- **multi_indicator** – multiple indicators on one stream
- **branching** – two computation branches from the same input
- **state_machine** – maintains a simple trend state

Each template is implemented in `qmtl/examples/templates/` and ends with a short
`Runner` invocation so you can execute the file directly. Choose a template
with the `--strategy` option when initializing your project:

```bash
qmtl init --path my_proj --strategy branching
```
