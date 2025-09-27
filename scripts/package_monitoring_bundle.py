"""Utilities to package monitoring Jsonnet bundles into Helm or Terraform artifacts."""
from __future__ import annotations

import argparse
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class Bundle:
    """Container for the monitoring bundle definition."""

    name: str
    version: int
    dashboards: List[Dict[str, Any]]
    recording_rules: List[Dict[str, Any]]

    @classmethod
    def from_path(cls, path: Path) -> "Bundle":
        data = json.loads(path.read_text())
        return cls(
            name=data["bundle"],
            version=int(data.get("version", 1)),
            dashboards=list(data.get("dashboards", [])),
            recording_rules=list(data.get("recordingRules", [])),
        )


class LiteralStr(str):
    """YAML literal block helper."""


def _literal_presenter(dumper: yaml.Dumper, data: LiteralStr):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralStr, _literal_presenter)
yaml.SafeDumper.add_representer(LiteralStr, _literal_presenter)


def build_helm(bundle: Bundle, output_dir: Path) -> None:
    chart_dir = output_dir / "helm" / bundle.name
    templates_dir = chart_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = output_dir.parent / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    (chart_dir / "Chart.yaml").write_text(
        textwrap.dedent(
            f"""
            apiVersion: v2
            name: {bundle.name}
            description: Helm chart generated from the {bundle.name} Jsonnet bundle.
            type: application
            version: {bundle.version}.0.0
            appVersion: "{bundle.version}"
            """
        ).strip()
        + "\n",
    )

    helpers_tpl = textwrap.dedent(
        f"""
        {{{{- define "{bundle.name}.name" -}}}}
        {{{{- default .Chart.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}}}
        {{{{- end -}}}}

        {{{{- define "{bundle.name}.fullname" -}}}}
        {{{{- if .Values.fullnameOverride -}}}}
        {{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}}}
        {{{{- else -}}}}
        {{{{- printf "%s-%s" (include "{bundle.name}.name" .) .Release.Name | trunc 63 | trimSuffix "-" -}}}}
        {{{{- end -}}}}
        {{{{- end -}}}}

        {{{{- define "{bundle.name}.labels" -}}}}
        app.kubernetes.io/name: {{{{ include "{bundle.name}.name" . }}}}
        app.kubernetes.io/instance: {{{{ .Release.Name }}}}
        app.kubernetes.io/version: {{{{ .Chart.AppVersion }}}}
        app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
        {{{{- if .Values.commonLabels }}}}
        {{{{- toYaml .Values.commonLabels | nindent 0 }}}}
        {{{{- end }}}}
        {{{{- end -}}}}
        """
    ).strip()

    (templates_dir / "_helpers.tpl").write_text(helpers_tpl + "\n")

    values = {
        "fullnameOverride": "",
        "commonLabels": {},
        "grafanaDashboards": {
            "enabled": bool(bundle.dashboards),
            "folder": bundle.name.replace("_", " ").title(),
            "dashboards": [],
        },
        "prometheusRule": {
            "enabled": bool(bundle.recording_rules),
            "namespace": "monitoring",
            "name": f"{bundle.name}-recording-rules",
            "groups": [],
        },
    }

    for dashboard in bundle.dashboards:
        dashboards_copy = dict(dashboard)
        dashboards_copy["json"] = LiteralStr(json.dumps(dashboard, indent=2))
        values["grafanaDashboards"]["dashboards"].append(dashboards_copy)

    if bundle.recording_rules:
        values["prometheusRule"]["groups"].append(
            {
                "name": f"{bundle.name}-recordings",
                "rules": [
                    {
                        "record": rule.get("name"),
                        "expr": rule.get("expr"),
                        "labels": rule.get("labels", {}),
                    }
                    for rule in bundle.recording_rules
                ],
            }
        )

    values_yaml = yaml.safe_dump(values, sort_keys=False)
    (chart_dir / "values.yaml").write_text(values_yaml)

    sample_values = {
        "fullnameOverride": f"{bundle.name}-prod",
        "commonLabels": {"team": "monitoring", "component": "seamless"},
        "grafanaDashboards": {
            "enabled": True,
            "folder": "Seamless",
            "dashboards": [
                {
                    "uid": d.get("uid"),
                    "title": d.get("title"),
                }
                for d in bundle.dashboards
            ],
        },
        "prometheusRule": {
            "enabled": bool(bundle.recording_rules),
            "namespace": "monitoring",
            "name": f"{bundle.name}-recording-rules",
        },
    }
    sample_yaml = yaml.safe_dump(sample_values, sort_keys=False)
    (chart_dir / "values-sample.yaml").write_text(sample_yaml)
    (samples_dir / f"{bundle.name}.helm-values.yaml").write_text(sample_yaml)

    dashboards_template = textwrap.dedent(
        """
        {{- if and .Values.grafanaDashboards.enabled (gt (len .Values.grafanaDashboards.dashboards) 0) }}
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: {{ include "%s.fullname" . }}-grafana
          labels:
            {{- include "%s.labels" . | nindent 4 }}
            grafana_dashboard: "1"
        data:
        {{- range $dashboard := .Values.grafanaDashboards.dashboards }}
          {{ $dashboard.uid }}.json: |
        {{ $dashboard.json | indent 4 }}
        {{- end }}
        {{- end }}
        """
        % (bundle.name, bundle.name)
    ).strip()
    (templates_dir / "grafana-dashboards.yaml").write_text(dashboards_template + "\n")

    prometheus_template = textwrap.dedent(
        """
        {{- if and .Values.prometheusRule.enabled (gt (len .Values.prometheusRule.groups) 0) }}
        apiVersion: monitoring.coreos.com/v1
        kind: PrometheusRule
        metadata:
          name: {{ .Values.prometheusRule.name }}
          namespace: {{ .Values.prometheusRule.namespace }}
          labels:
            {{- include "%s.labels" . | nindent 4 }}
        spec:
          groups:
          {{- toYaml .Values.prometheusRule.groups | nindent 4 }}
        {{- end }}
        """
        % bundle.name
    ).strip()
    (templates_dir / "prometheus-rules.yaml").write_text(prometheus_template + "\n")

    (chart_dir / "README.md").write_text(
        textwrap.dedent(
            f"""
            # {bundle.name} Helm Chart

            This chart is generated from the `{bundle.name}` monitoring Jsonnet bundle. It
            creates a ConfigMap for Grafana dashboards and an optional PrometheusRule for
            recording rules. Adjust `values.yaml` or provide custom values during Helm
            installation to fit your environment.
            """
        ).strip()
        + "\n",
    )


def build_terraform(bundle: Bundle, output_dir: Path) -> None:
    module_dir = output_dir / "terraform" / bundle.name
    module_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = output_dir.parent / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    dashboards_json = json.dumps(bundle.dashboards, indent=2)
    recording_json = json.dumps(
        [
            {
                "record": rule.get("name"),
                "expr": rule.get("expr"),
                "labels": rule.get("labels", {}),
            }
            for rule in bundle.recording_rules
        ],
        indent=2,
    )

    main_tf = textwrap.dedent(
        f"""
        terraform {{
          required_version = ">= 1.2.0"
        }}

        variable "name" {{
          description = "Base name used for generated resources"
          type        = string
          default     = "{bundle.name}"
        }}

        variable "namespace" {{
          description = "Kubernetes namespace where resources will be created"
          type        = string
          default     = "monitoring"
        }}

        variable "labels" {{
          description = "Additional labels applied to generated objects"
          type        = map(string)
          default     = {{}}
        }}

        variable "create_grafana_configmap" {{
          description = "Whether to create the Grafana dashboard ConfigMap"
          type        = bool
          default     = true
        }}

        variable "create_prometheus_rule" {{
          description = "Whether to create the PrometheusRule resource"
          type        = bool
          default     = {"true" if bundle.recording_rules else "false"}
        }}

        locals {{
          dashboards = jsondecode(<<EOT
        {dashboards_json}
        EOT
          )

          recording_rules = jsondecode(<<EOR
        {recording_json}
        EOR
          )
        }}

        resource "kubernetes_config_map" "grafana_dashboards" {{
          count = var.create_grafana_configmap && length(local.dashboards) > 0 ? 1 : 0

          metadata {{
            name      = "${{var.name}}-grafana-dashboards"
            namespace = var.namespace
            labels    = merge({{"grafana_dashboard" = "1"}}, var.labels)
          }}

          data = {{ for dashboard in local.dashboards : "${{dashboard.uid}}.json" => jsonencode(dashboard) }}
        }}

        resource "kubernetes_manifest" "prometheus_rule" {{
          count = var.create_prometheus_rule && length(local.recording_rules) > 0 ? 1 : 0

          manifest = {{
            apiVersion = "monitoring.coreos.com/v1"
            kind       = "PrometheusRule"
            metadata = {{
              name      = "${{var.name}}-recording-rules"
              namespace = var.namespace
              labels    = var.labels
            }}
            spec = {{
              groups = [{{
                name  = "{bundle.name}-recordings"
                rules = local.recording_rules
              }}]
            }}
          }}
        }}

        output "dashboards" {{
          description = "Rendered dashboard definitions"
          value       = local.dashboards
        }}

        output "recording_rules" {{
          description = "Rendered recording rule definitions"
          value       = local.recording_rules
        }}
        """
    ).strip()
    (module_dir / "main.tf").write_text(main_tf + "\n")

    variables_example = textwrap.dedent(
        """
        # Example Terraform variable overrides for CI/CD automation.
        name      = "seamless"
        namespace = "observability"
        labels = {
          team      = "monitoring"
          component = "seamless"
        }
        create_grafana_configmap = true
        create_prometheus_rule   = true
        """
    ).strip()
    (module_dir / "terraform.tfvars.example").write_text(variables_example + "\n")
    (samples_dir / f"{bundle.name}.terraform.tfvars").write_text(variables_example + "\n")

    readme = textwrap.dedent(
        f"""
        # {bundle.name} Terraform module

        This module exposes the dashboards and recording rules contained in the
        `{bundle.name}` Jsonnet bundle. It provisions a Grafana dashboard ConfigMap
        and an optional PrometheusRule using the Kubernetes provider.
        """
    ).strip()
    (module_dir / "README.md").write_text(readme + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("operations/monitoring/seamless_v2.jsonnet"),
        help="Path to the monitoring Jsonnet bundle",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("operations/monitoring/dist"),
        help="Directory where packaging artifacts will be written",
    )
    parser.add_argument(
        "--format",
        choices=("helm", "terraform", "all"),
        default="all",
        help="Artifact format to generate",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle = Bundle.from_path(args.input)

    if args.format in {"helm", "all"}:
        build_helm(bundle, args.output)
    if args.format in {"terraform", "all"}:
        build_terraform(bundle, args.output)


if __name__ == "__main__":
    main()
