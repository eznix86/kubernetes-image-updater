# Kubernetes Image Updater

A minimal Kopf-based operator that restarts annotated Kubernetes workloads when the OCI digest behind their tagged image changes. See `docs/spec.md` for the public specification.

## Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv) for repeatable local testing and mirrored in `uv.lock`.

```bash
uv venv
source .venv/bin/activate
uv sync
uv run kopf run operator.py
```

## Helm Chart

Package and deploy the operator via the bundled Helm chart:

```bash
helm install image-updater charts/kubernetes-image-updater \
  --set image.repository=yourrepo/image-updater \
  --set image.tag=$(git rev-parse --short HEAD)
```

Annotate workloads with `image-updater.eznix86.github.io/enabled: "true"` to opt in.
