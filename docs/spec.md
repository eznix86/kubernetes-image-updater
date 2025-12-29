## 1. Overview

Kubernetes Image Updater watches annotated workloads and periodically compares the OCI digest of their **current** container image to the digest that last triggered a rollout. If the registry answers with a new digest, the operator patches the workload’s pod template with `kubectl.kubernetes.io/restartedAt`, causing Kubernetes to perform a standard rolling restart. No tags are rewritten, no Git state is touched, and no pods are deleted manually.

Key characteristics:

- Works with existing tags (e.g., `nginx:stable`, `ghcr.io/org/app:prod`).
- Tracks **all containers** in `spec.template.spec.containers` by default (configurable via annotations).
- Optionally tracks init containers via `track-init-containers="true"`.
- Stores digests for all tracked containers in a single `last-digest` annotation.
- Triggers rollout when ANY tracked container's digest changes.
- Leaves rollout strategy, autoscaling, and disruption budgets entirely to Kubernetes.

---

## 2. Supported Workloads

The controller interacts with native controllers that expose a pod template:

| Supported        | Not Supported            |
| ---------------- | ------------------------ |
| Deployments      | Standalone Pods          |
| StatefulSets     | Jobs / CronJobs          |
| DaemonSets       | Static Pods              |
| ReplicaSets\*    |                          |

\*ReplicaSets inherit support through Deployments; they are not watched directly.

---

## 3. Annotation Reference

| Annotation Key                                      | Written By  | Meaning |
| --------------------------------------------------- | ----------- | ------- |
| `image-updater.eznix86.github.io/enabled`           | User        | Set to `"true"` on a workload to opt in. Absent or other values mean "ignore." |
| `image-updater.eznix86.github.io/track-containers`  | User        | Comma-separated list of container names from `spec.containers` to track. If set, only these containers are monitored. If not set, behavior depends on `ignore-containers`. |
| `image-updater.eznix86.github.io/ignore-containers` | User        | Comma-separated list of container names from `spec.containers` to exclude from tracking. Ignored if `track-containers` is set. |
| `image-updater.eznix86.github.io/track-init-containers` | User | Set to `"true"` to include all `spec.initContainers` in tracking. Default is `"false"`. |
| `image-updater.eznix86.github.io/last-digest`       | Operator    | Stores digests for all tracked containers in format `"<name>:<digest>,<name>:<digest>"`. Used for idempotency. Entries are alphabetically sorted. Automatically migrates from legacy single-digest format. |
| `kubectl.kubernetes.io/restartedAt`                 | Operator    | Standard Kubernetes annotation used to trigger a rollout restart by mutating `spec.template.metadata.annotations`. |

All operator-managed annotations live under `image-updater.eznix86.github.io/*` and should be treated as internal state.

---

## 4. Reconciliation Flow

1. **Discovery** – Kopf timers target Deployments, StatefulSets, and DaemonSets in the `apps/v1` API group. Resources lacking the enable annotation are skipped immediately.
2. **Container selection** – The controller determines which containers to track:
   - From `spec.template.spec.containers`: all containers by default, unless `track-containers` or `ignore-containers` is set.
   - From `spec.template.spec.initContainers`: all init containers if `track-init-containers="true"`.
3. **Digest resolution** – For each tracked container, the controller parses the image reference, infers a registry when needed (Docker Hub with the `library/` prefix for bare names), and performs an HTTP `GET /v2/<repo>/manifests/<tag>` with `Accept: application/vnd.docker.distribution.manifest.v2+json`. The digest is taken from the `Docker-Content-Digest` header.
4. **Comparison** – Each digest is compared to the corresponding entry in `image-updater.eznix86.github.io/last-digest` (format `"<name>:<digest>,<name>:<digest>"`). Legacy single-digest format is automatically migrated to the new format.
5. **Restart trigger** – When ANY tracked container's digest differs or is missing from the annotation, the controller:
    - Writes all current digests (for all tracked containers) to `image-updater.eznix86.github.io/last-digest`; and
    - Patches `spec.template.metadata.annotations` with a fresh ISO-8601 timestamp at `kubectl.kubernetes.io/restartedAt`.
6. **Rollout** – Kubernetes controllers pick up the template change and roll out according to their own strategy. The operator does nothing else until the next timer tick.

Failures when reaching the registry (timeouts, `401 Unauthorized`, etc.) are logged and the reconciliation exits without mutating the workload. State remains unchanged until the next timer attempt.

---

## 5. Image Resolution Details

- **Registry inference** – Image names without an explicit registry use `registry-1.docker.io`. Names without a slash are rewritten as `library/<name>` to align with Docker Hub conventions.
- **Accepted schemes** – Any registry that implements the Docker Registry HTTP API v2 works (Docker Hub, GHCR, Quay, private registries, etc.).
- **Authentication** – The controller relies on the same credentials available to the node or cluster (e.g., pre-configured `/var/lib/kubelet/config.json`, `imagePullSecrets`, or public registries). No additional auth wiring is performed.

---

## 6. Failure Behavior

- Registry errors are surfaced via warning logs and the loop continues on the next interval. There is no retry inside a single tick.
- Workloads without containers or without an `image` value are ignored for that pass.
- Only the annotation fields mentioned above are patched; no other metadata or spec fields are touched (unless the optional pull-policy override below is enabled).

---

## 7. Optional Pull-Policy Override

By default the operator expects annotated workloads to use `imagePullPolicy: Always` or digest-pinned images. For convenience, the Helm chart ships with `automaticallySetImagePullPolicy=true`, which sets the environment variable `AUTOMATICALLY_SET_IMAGE_PULL_POLICY_TO_ALWAYS=true`. When enabled, the controller patches every declared container (in `spec.containers`) to `imagePullPolicy: Always` before triggering the restart. This ensures kubelets repull tags such as `:latest` even when the workload originally used `IfNotPresent`.

- All containers in `spec.containers` are modified in one patch (init containers are not modified).
- The patch happens as part of the same rollout mutation, so the workload ends up with the `Always` policy after the reconciliation. If you disable the feature later, you should revert the workload spec yourself.

---

## 8. Access Requirements

To function, the controller needs:

- **Read** access to Deployments, StatefulSets, and DaemonSets for discovery.
- **Patch** access on those resources so it can mutate metadata and pod templates.

Pods are never deleted directly, and scaling decisions remain with the native controllers.

---

## 9. Compatibility & Non-Goals

The behavior intentionally mirrors `kubectl rollout restart`, making it compatible with:

- GitOps tools such as Flux or Argo CD (they see standard template annotations).
- Autoscalers, PodDisruptionBudgets, and other built-in controllers.

Explicitly out of scope:

- Selecting “latest” images on behalf of the user or performing semantic version comparisons.
- Managing Git repositories, manifests, or CI/CD pipelines.
- Acting as a policy or verification layer — it simply observes digests and restarts.

---

## 10. Development & Testing

### Local Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv) for repeatable local testing:

```bash
uv sync                    # Install dependencies
uv run kopf --all-namespaces run controller.py  # Run locally with current kubeconfig
```

### Testing

The project includes comprehensive pytest tests covering core functionality:

```bash
uv sync --group dev        # Install test dependencies (pytest, pytest-mock, ruff)
uv run ruff check .        # Run code linting
uv run pytest              # Run all tests
uv run pytest tests/test_domain.py -v  # Run specific test file
```

Test coverage includes:
- Domain models (ImageReference, DigestMap, ContainerInfo)
- Container selection logic with various annotation combinations
- Image registry authentication and parsing
- Reconciliation logic and error handling

All tests are designed to run quickly without external dependencies.

---

## 11. Installation Notes

The published Helm chart defaults to a dedicated namespace so it can be installed with a single command:

```bash
helm repo add eznix86 https://eznix86.github.io/kubernetes-image-updater
helm repo update

helm install image-updater eznix86/kubernetes-image-updater \
  --namespace image-updater \
  --create-namespace
```

Values can override the namespace or image repository as needed, but the example above is ready to copy/paste.

---

## 12. Summary

Digest changes for any tracked container turn into Kubernetes-native rollout restarts for annotated workloads. That’s the entire contract: **any tracked container digest change → workload annotation update → Kubernetes performs the rollout.**
