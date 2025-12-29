# Kubernetes Image Updater

Similar to [containerr/watchtower](https://github.com/containrrr/watchtower), this Kubernetes operator will automatically restart Kubernetes workloads when container image digests change. Perfect for homelabs and environments where you want `:latest` or `:stable` tags to stay up-to-date without GitOps.

## Use Cases

- Homelabs
- Where tracking `:latest` tags is not a problem and want automatic rollouts when registries publish new digests.
- You do not want Gitops (Manualops?), but you want your images with `:latest`, `:stable`\* to be always up to date.

\* it can be any tags, but the standard is `:latest`.

## Get Started

### 1. Install the operator

```bash
helm repo add eznix86 https://eznix86.github.io/kubernetes-image-updater
helm repo update

helm install image-updater eznix86/kubernetes-image-updater \
  --namespace image-updater \
  --create-namespace
```

### 2. Annotate your workload

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  annotations:
    image-updater.eznix86.github.io/enabled: "true"
spec:
  template:
    spec:
      containers:
      - name: app
        image: nginx:latest  # Will auto-restart when digest changes
```

### 3. Done!

The operator will now monitor your images and automatically restart workloads whenever the registry publishes new digests.

## Configuration

### Pull Policy Override

By default, the operator assumes workloads use `imagePullPolicy: Always`. For convenience, the chart will automatically override your pull policy:

```bash
helm install image-updater eznix86/kubernetes-image-updater \
  --namespace image-updater \
  --create-namespace \
  --set automaticallySetImagePullPolicy=true
```

When enabled, tracked containers are temporarily set to `imagePullPolicy: Always` before restart.

### Configuration Examples

#### Basic usage (track all containers)
```yaml
annotations:
  image-updater.eznix86.github.io/enabled: "true"
```

#### Track only specific containers
```yaml
annotations:
  image-updater.eznix86.github.io/enabled: "true"
  image-updater.eznix86.github.io/track-containers: "app,worker"
```

#### Ignore specific containers
```yaml
annotations:
  image-updater.eznix86.github.io/enabled: "true"
  image-updater.eznix86.github.io/ignore-containers: "log-collector,metrics"
```

#### Include init containers
```yaml
annotations:
  image-updater.eznix86.github.io/enabled: "true"
  image-updater.eznix86.github.io/track-init-containers: "true"
```

#### Advanced: Track specific containers + init containers
```yaml
annotations:
  image-updater.eznix86.github.io/enabled: "true"
  image-updater.eznix86.github.io/track-containers: "app,worker"
  image-updater.eznix86.github.io/track-init-containers: "true"
```

### All Available Annotations

| Annotation | Required | Description | Values | Default |
|-----------|----------|-------------|--------|---------|
| `image-updater.eznix86.github.io/enabled` | Required | Enable operator for this workload | `"true"` or `"false"` | `"false"` |
| `image-updater.eznix86.github.io/track-containers` | Optional | Only track these specific containers | `"container1,container2"` | All containers |
| `image-updater.eznix86.github.io/ignore-containers` | Optional | Ignore these containers from tracking | `"container1,container2"` | None |
| `image-updater.eznix86.github.io/track-init-containers` | Optional | Include init containers in tracking | `"true"` or `"false"` | `"false"` |
| `image-updater.eznix86.github.io/last-digest` | Optional | Stores container digest map (managed by operator) | Auto-generated | None |

**Notes:**
- `track-containers` takes precedence over `ignore-containers` if both are specified
- `last-digest` is automatically managed by the operator and should not be set manually
- `kubectl.kubernetes.io/restartedAt` is automatically added by the operator for rollouts

## Supported Workloads

- Deployments
- StatefulSets
- DaemonSets
- ReplicaSets (via Deployments)

## Development

### Local Testing

```bash
uv sync --group dev  # Install dependencies
uv run ruff check .  # Code linting
uv run pytest        # Run tests
uv run kopf run controller.py  # Run operator locally
```

### Building

```bash
uv sync  # Install dependencies
docker build -t image-updater .  # Build container
```
