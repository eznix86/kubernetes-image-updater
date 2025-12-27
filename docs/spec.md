# Kubernetes Image Updater — Information Sheet

**Project:** Kubernetes Image Updater  
**Repository:** [https://github.com/eznix86/kubernetes-image-updater](https://github.com/eznix86/kubernetes-image-updater)  
**Status:** Stable (v1)  
**Purpose:** Restart Kubernetes workloads when the OCI digest behind their current tag changes  
**Intended Environments:** Homelabs, personal clusters, or any setup where `:latest` or manual tag pinning is acceptable

---

## 1. Overview

Kubernetes Image Updater watches annotated workloads and periodically compares the OCI digest of their **current** container image to the digest that last triggered a rollout. If the registry answers with a new digest, the operator patches the workload’s pod template with `kubectl.kubernetes.io/restartedAt`, causing Kubernetes to perform a standard rolling restart. No tags are rewritten, no Git state is touched, and no pods are deleted manually.

Key characteristics:

- Works with existing tags (e.g., `nginx:stable`, `ghcr.io/org/app:prod`).
- Uses the **first** container in the pod spec for digest checks in v1.
- Stores the last observed digest on the workload itself to avoid duplicate restarts.
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
| `image-updater.eznix86.github.io/enabled`           | User        | Set to `"true"` on a workload to opt in. Absent or other values mean “ignore.” |
| `image-updater.eznix86.github.io/last-digest`       | Operator    | Stores the digest that most recently triggered a restart. Used for idempotency. |
| `kubectl.kubernetes.io/restartedAt`                 | Operator    | Standard Kubernetes annotation used to trigger a rollout restart by mutating `spec.template.metadata.annotations`. |

All operator-managed annotations live under `image-updater.eznix86.github.io/*` and should be treated as internal state.

---

## 4. Reconciliation Flow

1. **Discovery** – Kopf timers target Deployments, StatefulSets, and DaemonSets in the `apps/v1` API group. Resources lacking the enable annotation are skipped immediately.
2. **Image selection** – The first entry in `spec.template.spec.containers` supplies the image reference.
3. **Digest resolution** – The controller parses the reference, infers a registry when needed (Docker Hub with the `library/` prefix for bare names), and performs an HTTP `GET /v2/<repo>/manifests/<tag>` with `Accept: application/vnd.docker.distribution.manifest.v2+json`. The digest is taken from the `Docker-Content-Digest` header.
4. **Comparison** – The digest is compared to `image-updater.eznix86.github.io/last-digest` stored on the workload metadata.
5. **Restart trigger** – When the digest differs, the controller:
   - Writes the new digest to the workload metadata; and
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
- Only the annotation fields mentioned above are patched; no other metadata or spec fields are touched.

---

## 7. Access Requirements

To function, the controller needs:

- **Read** access to Deployments, StatefulSets, and DaemonSets for discovery.
- **Patch** access on those resources so it can mutate metadata and pod templates.

Pods are never deleted directly, and scaling decisions remain with the native controllers.

---

## 8. Compatibility & Non-Goals

The behavior intentionally mirrors `kubectl rollout restart`, making it compatible with:

- GitOps tools such as Flux or Argo CD (they see standard template annotations).
- Autoscalers, PodDisruptionBudgets, and other built-in controllers.

Explicitly out of scope:

- Selecting “latest” images on behalf of the user or performing semantic version comparisons.
- Managing Git repositories, manifests, or CI/CD pipelines.
- Acting as a policy or verification layer — it simply observes digests and restarts.

---

## 9. Summary

Digest changes turn into Kubernetes-native rollout restarts for annotated workloads. That’s the entire contract: **digest change → workload annotation update → Kubernetes performs the rollout.**
