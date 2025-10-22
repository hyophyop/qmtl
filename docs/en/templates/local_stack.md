---
title: "Local Stack Configuration Template"
tags: [templates, local]
author: "QMTL Team"
last_modified: 2025-09-24
---

{{ nav_links() }}

# Local Stack Configuration Template

For lightweight development setups, use
{{ code_link('qmtl/examples/templates/local_stack.example.yml', text='`qmtl/examples/templates/local_stack.example.yml`') }}.
It provisions the minimal Redis, SQLite, and mock messaging services required to
exercise Gateway, DAG Manager, and WorldService without external dependencies.

## Customization Checklist

- Update the `QMTL_*` environment variables to point at your project-specific
databases and topic prefixes.
- Toggle optional services (Redis, Kafka shim) by commenting them out or adjusting
ports to avoid local conflicts.
- Extend the compose file with additional tooling (e.g., Jaeger, Tempo) as needed.

## Quick Copy Command

```bash
python - <<'PY'
import importlib.resources as resources
path = resources.files('qmtl.examples').joinpath('templates/local_stack.example.yml')
print(path)
PY
```

Use the printed path with `cp` to duplicate the template into your workspace.

{{ nav_links() }}
