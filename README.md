# Kubernetes Image Updater

A lightweight Kubernetes helper that re-rolls annotated workloads whenever the digest behind their current image tag changes. See `docs/spec.md` for the full behavior.

## Use cases

- Homelabs
- Where tracking `:latest` tags is not a problem and want automatic rollouts when registries publish new digests.


### Supported

The controller interacts with native controllers that expose a pod template:

| Supported        | Not Supported            |
| ---------------- | ------------------------ |
| Deployments      | Standalone Pods          |
| StatefulSets     | Jobs / CronJobs          |
| DaemonSets       | Static Pods              |
| ReplicaSets\*    |                          |

\*ReplicaSets inherit support through Deployments; they are not watched directly.

### Requirements

The operator only triggers rollouts; Kubernetes decides whether a node repulls the image. Configure your workloads with `imagePullPolicy: Always` (or use digest-pinned tags) so restarts actually fetch new layers. If that isn’t practical, enable the optional automation described below.

## Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv) for repeatable local testing and mirrored in `uv.lock`.

```bash
uv venv
source .venv/bin/activate
uv sync
# will use your current kubeconfig
uv run kopf --all-namespaces run controller.py
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

### Optional pull-policy override

Set `.Values.automaticallySetImagePullPolicy=true` (or the `AUTOMATICALLY_SET_IMAGE_PULL_POLICY_TO_ALWAYS` env var in custom deployments) if you want the operator to temporarily patch annotated workloads to `imagePullPolicy: Always` before each restart:

```bash
helm install image-updater eznix86/kubernetes-image-updater \
  --namespace image-updater \
  --create-namespace \
  --set automaticallySetImagePullPolicy=true
```

### Required annotation

```yaml
metadata:
  annotations:
    image-updater.eznix86.github.io/enabled: "true"
```

The operator manages only annotated resources; it ignores everything else.
