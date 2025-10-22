---
title: "Backend Stack Configuration Template"
tags: [templates, backend]
author: "QMTL Team"
last_modified: 2025-09-24
---

{{ nav_links() }}

# Backend Stack Configuration Template

The production-oriented Compose bundle that powers Gateway, DAG Manager,
WorldService, and the supporting infrastructure lives in
{{ code_link('qmtl/examples/templates/backend_stack.example.yml', text='`qmtl/examples/templates/backend_stack.example.yml`') }}.
Copy that file when you need a starting point for a full deployment and adjust the
service images, credentials, and hostnames to match your environment.

## Services

The template stands up Redis, Postgres, Kafka, Neo4j, Prometheus/Grafana, and the
core QMTL services. Update the following sections before running `docker compose`:

- `x-qmtl-image:` blocks – swap in the tagged images for your registry.
- `volumes:` – adjust host paths for persistent data (Postgres, Neo4j, Prometheus).
- `environment:` – replace placeholder secrets and connection strings.
- `depends_on:` – drop services you do not plan to operate.

## Usage Tips

1. Copy the template to your project:

   ```bash
   cp $(python -c "import importlib.resources as r; print(r.files('qmtl.examples').joinpath('templates/backend_stack.example.yml'))") ./templates/backend_stack.yml
   ```

2. Update the copied file and commit it with your project scaffolding.
3. Run the stack locally or in CI with `docker compose -f templates/backend_stack.yml up -d`.

{{ nav_links() }}
