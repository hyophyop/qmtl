# Strategy Guidelines

- Implement node processors as pure functions under `nodes/` so they can be reused across DAGs.
- Define strategy DAGs in `dags/` using `qmtl.dag_manager` for orchestration.
- Connect nodes by wiring explicit output keys to input parameters; the graph must remain acyclic and each node name unique.
- Use `snake_case` for file and function names. Name node processor functions with the `_node` suffix and DAG modules with the `_dag.py` suffix.

