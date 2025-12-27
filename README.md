# Kubernetes Image Updater

A lightweight Kubernetes helper that re-rolls annotated workloads whenever the digest behind their current image tag changes. See `docs/spec.md` for the full behavior.

## Use cases

- Homelabs or personal clusters that track `:latest` tags and want automatic rollouts when registries publish new digests.
- Small teams pinning images manually but needing a digest watcher without wiring a full GitOps stack.
- **Warning:** This project is *not* hardened for production. There is no HA story, no admission control, and no guarantees around RBAC or audit requirements—run it only in environments where those gaps are acceptable.

## Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv) for repeatable local testing and mirrored in `uv.lock`.

```bash
uv venv
source .venv/bin/activate
uv sync
uv run kopf run controller.py
```

## Helm Chart

Install the published chart directly from GitHub:

```bash
helm repo add eznix86 https://eznix86.github.io/kubernetes-image-updater
helm repo update

helm install image-updater eznix86/kubernetes-image-updater \
  --namespace image-updater \
  --create-namespace
```

### Required annotation

Opt specific workloads in with the GitHub-hosted annotation namespace:

```yaml
metadata:
  annotations:
    image-updater.eznix86.github.io/enabled: "true"
```

The operator manages only annotated resources; it ignores everything else.
