# Example Terraform variable overrides for CI/CD automation.
name      = "seamless"
namespace = "observability"
labels = {
  team      = "monitoring"
  component = "seamless"
}
create_grafana_configmap = true
create_prometheus_rule   = true
