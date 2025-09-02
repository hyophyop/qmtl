# Commit Log Configuration

Gateway can optionally publish and consume commit-log records via Kafka. The
settings below live under the `gateway` section of the YAML configuration
file.

```yaml
gateway:
  commitlog_bootstrap: "localhost:9092"
  commitlog_topic: "commit-log"
  commitlog_group: "gateway-commits"
  commitlog_transactional_id: "gateway-writer"
```

- `commitlog_bootstrap` – Kafka bootstrap servers for commit-log topics.
- `commitlog_topic` – Compacted topic storing commit-log records.
- `commitlog_group` – Consumer group id used by Gateway when processing the
  commit log.
- `commitlog_transactional_id` – Transactional id for the commit-log writer's
  idempotent producer.

When configured, Gateway will start a `CommitLogConsumer` in its event loop and
route deduplicated records to its processing callback. On shutdown the consumer
is stopped and the writer's producer is closed.
