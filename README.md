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

The operator only triggers rollouts; Kubernetes decides whether a node repulls the image. Configure your workloads with `imagePullPolicy: Always` (or use digest-pinned tags) so restarts actually fetch new layers. If that isn't practical, enable the optional automation described below.

## Rolling Update Behavior

The operator uses **Kubernetes native rolling updates**, not in-place pod deletion:

- Adds `kubectl.kubernetes.io/restartedAt` annotation to pod template
- Kubernetes detects pod template change and initiates rolling update
- Follows workload's `updateStrategy` (RollingUpdate by default)
- **Zero downtime** for Deployments with proper readiness probes

| Workload | Default Update Strategy | Behavior |
|-----------|-----------------------|----------|
| Deployment | RollingUpdate | Gradual pod replacement controlled by `maxUnavailable`/`maxSurge` |
| StatefulSet | RollingUpdate | Sequential replacement respecting ordinal index |
| DaemonSet | RollingUpdate | Node-by-node pod replacement |

This is identical to `kubectl rollout restart deployment/<name>`.

## Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv) for repeatable local testing and mirrored in `uv.lock`.

```bash
uv venv
uv sync
# will use your current kubeconfig
uv run kopf --all-namespaces run controller.py
```

## Testing

The project includes comprehensive pytest tests covering core functionality, domain models, and integration logic.

### Install test dependencies

```bash
uv sync --group dev
```

### Run tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_domain.py -v

# Run tests with coverage (if installed)
uv run pytest --cov=controller --cov-report=html
```

### Test structure

- **`test_domain.py`**: Domain models (ImageReference, ContainerInfo, DigestMap, etc.)
- **`test_container_selector.py`**: Container selection logic with various annotation combinations
- **`test_image_registry_basic.py`**: Basic ImageRegistry functionality
- **`test_reconciler_simple.py`**: Core reconciler logic

All tests are designed to run quickly without external dependencies, using mocks where necessary.

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

This behavior is enabled by default. Leave `.Values.automaticallySetImagePullPolicy=true` (or the `AUTOMATICALLY_SET_IMAGE_PULL_POLICY_TO_ALWAYS` env var) to keep it, or set it to `false` to opt out. When enabled, the operator temporarily patches every container in annotated workloads to `imagePullPolicy: Always` before each restart:

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
