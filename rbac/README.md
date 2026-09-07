# RBAC

Two roles, as required by the project spec:

| Group | Staging | Production |
|---|---|---|
| `mlops-engineer` | Full access (`mlops-engineer-role-staging.yaml`) | Restricted — read-only + `patch` on Deployments only, for `kubectl rollout restart` (`mlops-engineer-role-production.yaml`) |
| `viewer` | Read-only, cluster-wide (`viewer-clusterrole.yaml`), secrets explicitly excluded | same |

## Applying

These are plain Kubernetes objects, not tied to any specific tool, so they're applied like any other manifest:
```bash
kubectl apply -f rbac/
```
(Not yet wired into the ArgoCD app-of-apps — `gitops/argocd/applications/` only tracks Application definitions, and these are cluster policy, not a workload. Apply once during cluster bootstrap, alongside the namespace phase in README.md.)

## Binding real people to these groups

Kubernetes `Group` subjects aren't objects you create — they come from whatever authenticates the request. For this EKS cluster, that means mapping an IAM principal to a Kubernetes group via an **EKS access entry**:

```bash
aws eks create-access-entry \
  --cluster-name goit-mlops-fp \
  --principal-arn arn:aws:iam::512523811086:user/<someone> \
  --kubernetes-groups mlops-engineer \
  --region us-east-1 --profile goit-terraform
```
(`--kubernetes-groups viewer` for the read-only role.)

This project has a single operator (one AWS IAM identity), so a second real IAM principal was never created just to demonstrate this — there's no one to bind it to. The two Roles/ClusterRole above are the actual deliverable; wiring a second engineer in is one `aws eks create-access-entry` call away whenever one exists.
