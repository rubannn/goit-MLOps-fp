# goit-MLOps-fp

MLOps-платформа на AWS EKS: Terraform-інфраструктура, ArgoCD (GitOps), MLflow Model Registry, Canary-деплой моделі рекомендацій (MovieLens), моніторинг та security baseline.

> Опорні напрацювання з попередніх ДЗ: `goit-MLOps` (Terraform/EKS), `goit-MLOps-argo` (ArgoCD/namespace-маніфести). Код перенесено й адаптовано під структуру цього репозиторію — вихідні репозиторії не змінювались.

## Модель і дані

- **Датасет:** [MovieLens ml-latest-small](https://grouplens.org/datasets/movielens/) (GroupLens Research) — публічний, ~100 000 рейтингів, ~9 000 фільмів.
- **Задача:** рекомендаційна система (Matrix Factorization).
- **Deployment-стратегія:** Canary (90/10) — обґрунтування в `ADR.md` (буде додано в Блоці D).

## Структура репозиторію

```
terraform/
  vpc/        — мережа (VPC, subnets)
  eks/        — EKS-кластер
  argocd/     — bootstrap ArgoCD (Helm) + ApplicationSet/Application, що тягнуть gitops/
gitops/
  namespace/  — по одному Application на namespace (staging, production, mlops-system, monitoring)
    staging/ns.yaml
    production/ns.yaml
    mlops-system/ns.yaml
    monitoring/ns.yaml
  argocd/applications/  — ArgoCD Application-маніфести сервісів (MLflow, MinIO, Postgres, Pushgateway, monitoring-stack)
```

Кожен файл під `terraform/*/backend.tf` вказує на окремий шлях у спільному S3-бакеті стану (`fp/vpc/...`, `fp/eks/...`, `fp/argocd/...`) — ізольовано від state попередніх ДЗ у тому ж бакеті.

## Namespace-и (EKS)

| Namespace | Призначення |
|---|---|
| `mlops-system` | Платформний інструментарій: ArgoCD, MLflow, MinIO, Postgres, Pushgateway |
| `monitoring` | Prometheus, Grafana, Loki (kube-prometheus-stack) |
| `staging` | Inference-сервіс — нова версія моделі перед промоушеном |
| `production` | Inference-сервіс — production-версія моделі, Canary-трафік |

## Розгортання з нуля (bootstrap-фази)

Bootstrap виконується у явних фазах — послідовність обов'язкова, кожна фаза залежить від попередньої.

### Передумови

- Terraform CLI ≥ 1.5
- AWS CLI, налаштований профіль `goit-terraform` з доступом до акаунту
- `kubectl`, `helm`
- Існуючий S3-бакет `mlops-tfstate-goit-512523811086` і DynamoDB-таблиця `mlops-tfstate-lock` (спільні для всіх ДЗ цього акаунту — вже створені раніше)

### Фаза 1 — мережа і кластер (Terraform)

```bash
cd terraform/vpc
terraform init
terraform apply

cd ../eks
terraform init
terraform apply
```

Перевірка:
```bash
aws eks update-kubeconfig --name <cluster_name> --region us-east-1 --profile goit-terraform
kubectl get nodes
```

### Фаза 2 — ArgoCD (Terraform + Helm)

```bash
cd ../argocd
terraform init
terraform apply
```

Це піднімає namespace `mlops-system`, встановлює ArgoCD через Helm і створює:
- `ApplicationSet` `gitops-namespaces`, що синхронізує все з `gitops/namespace/*` (по одному Application на namespace)
- `Application` `gitops-applications`, що синхронізує все з `gitops/argocd/applications` (сервіси)

> ⚠️ Готча (з попереднього ДЗ): CRD ArgoCD з'являються лише після встановлення Helm-релізу — на чистому кластері `kubernetes_manifest` для `ApplicationSet`/`Application` може впасти з першої спроби. Якщо так — повторний `terraform apply` після появи CRD вирішує проблему (в коді це враховано через `depends_on = [helm_release.argocd]`, але timing CRD registration інколи вимагає повторного запуску).

Перевірка:
```bash
kubectl get pods -n mlops-system
kubectl port-forward svc/argocd-server -n mlops-system 8080:443
# відкрити https://localhost:8080, логін admin / (пароль з kubectl -n mlops-system get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
```

### Фаза 3 — решта сервісів (через ArgoCD, GitOps)

Нічого руками запускати не треба — ArgoCD автоматично підхоплює `gitops/argocd/applications/*.yaml` і розгортає MLflow, MinIO, Postgres, Pushgateway (у `mlops-system`) та monitoring-stack (у `monitoring`).

Перевірка:
```bash
kubectl get applications -n mlops-system
# усі мають бути Synced / Healthy
```

### Доступ до сервісів

MLflow і Grafana доступні через port-forward (обґрунтування: без публічного Ingress/DNS для навчального проєкту — простіше й безпечніше для тимчасово піднятої на ~24 год інфраструктури):

```bash
kubectl port-forward svc/mlflow -n mlops-system 5000:5000
kubectl port-forward svc/monitoring-stack-grafana -n monitoring 3000:80
```

## Прибирання ресурсів (після кожної робочої сесії)

```bash
cd terraform/argocd && terraform destroy
cd ../eks && terraform destroy
cd ../vpc && terraform destroy
```

Порядок зворотний до розгортання (спочатку те, що залежить, потім базове).

## Відомі обмеження (буде виправлено найближчим часом)

- MinIO/Postgres/MLflow мають хардкоджені креденшели прямо в `gitops/argocd/applications/*.yaml` — винесення в Kubernetes Secret заплановано в Блоці C (security baseline).
- `mlops-system` namespace створюється двічі за задумом: спочатку напряму Terraform-ом (`kubernetes_namespace.argocd` — потрібен до встановлення самого ArgoCD, класична проблема "курки і яйця"), потім ще раз декларативно через `gitops/namespace/mlops-system/ns.yaml` під управлінням ArgoCD (ідемпотентно, конфлікту не викликає, ArgoCD просто бере existing namespace під GitOps-управління).
