# RUNBOOK

Операційні процедури для MovieLens MLOps-платформи. Усі команди передбачають, що `kubectl` вказує на кластер `goit-mlops-fp` (`aws eks update-kubeconfig --name goit-mlops-fp --region us-east-1 --profile goit-terraform`) і що MLflow доступний через port-forward (`kubectl port-forward svc/mlflow -n mlops-system 5000:5000`).

## Як викотити нову версію моделі

1. **Тренування** — тренує кілька комбінацій гіперпараметрів, логує в MLflow, автоматично реєструє найкращий run і переводить його у стадію **Staging**:
   ```bash
   cd experiments
   python train_and_push.py
   ```
   Нова версія одразу доступна для canary-подів (`movielens-inference-canary` у `production`, `MODEL_STAGE=Staging`) — при наступному рестарті поду вона підхопить нову модель без додаткових дій, бо under the hood `models:/movielens-recommender/Staging` завжди резолвиться в найновішу версію цієї стадії.

2. **Оцінка canary** — подивіться на Grafana-дашборд "MovieLens Inference Service" (розділ Request rate / Latency / Error rate), відфільтрувавши по `pod=~"movielens-inference-canary.*"`, і порівняйте з `stable`. За потреби перезапустіть canary-под, щоб він явно підхопив найновішу Staging-версію:
   ```bash
   kubectl rollout restart deployment/movielens-inference-canary -n production
   ```

3. **Promotion у Production** — окрема, явна дія (НЕ відбувається автоматично після тренування):
   ```bash
   cd experiments
   python promote_model.py            # промоутить найновішу Staging-версію
   # або конкретну версію:
   python promote_model.py --version 5
   kubectl rollout restart deployment/movielens-inference-stable -n production
   ```
   Стара Production-версія автоматично переходить у Archived (rollback залишається можливим).

## Як зробити rollback

Одна команда — відкочує MLflow Model Registry (Production → попередня версія, невдала → Archived) і перезапускає `stable`-деплоймент:
```bash
cd experiments
python rollback_model.py
```
Скрипт читає тег `previous_production_version`, який `promote_model.py` проставляє на кожній щойно промоутнутій версії — тому працює лише для версій, промоутнутих через `promote_model.py` (не вручну через MLflow UI).

Перевірка після rollback:
```bash
python -c "
from mlflow.tracking import MlflowClient
c = MlflowClient(tracking_uri='http://localhost:5000')
for mv in c.search_model_versions(\"name='movielens-recommender'\"):
    print(f'v{mv.version}: {mv.current_stage}')
"
kubectl get pods -n production
```

## Що робити, якщо Grafana показує latency > X

1. Відкрити дашборд "MovieLens Inference Service" → панель "Latency p50/p95" → визначити, чи проблема на `/predict`, `/recommend`, чи обидва.
2. Перевірити ресурси подів (панель CPU/RAM) — якщо под впирається в `limits` (500m CPU / 512Mi), масштабувати:
   ```bash
   kubectl scale deployment/movielens-inference-stable -n production --replicas=12
   ```
3. Перевірити логи в Loki (панель "Inference service logs" або напряму):
   ```bash
   kubectl logs -n production -l app=movielens-inference,track=stable --tail=100
   ```
   Шукати повторювані `"unhandled exception"` або аномально високий `latency_ms` у конкретних запитах.
4. Якщо проблема — повільне звернення до MLflow/MinIO (перше завантаження моделі на under, ~ 5-10с), а не сталий стан — це очікувано при **холодному старті** поду (модель кешується через `lru_cache` після першого запиту). Якщо це трапляється на кожному новому поді при масштабуванні — розглянути `initContainer`, що прогріває модель до відкриття readiness.
5. Якщо латентність стабільно висока і не деградує — перевірити мережеву затримку до `mlflow.mlops-system.svc.cluster.local`/`minio.mlops-system.svc.cluster.local` (`kubectl exec` в под і `curl -w "%{time_total}"`).

## Що робити, якщо Evidently показує data drift

> ⚠️ Evidently AI ще не інтегрований (Блок E, рекомендований, не обов'язковий) — цей розділ буде доповнено, коли з'явиться CronJob.

Загальний план дій, коли з'явиться:
1. Подивитись, які саме ознаки/розподіл прогнозованих рейтингів "попливли" — драйфт-метрики пишуться в Prometheus.
2. Перевірити, чи це закономірна зміна (нові фільми/користувачі в `ratings.csv`) чи ознака деградації моделі.
3. Якщо деградація підтверджена — перетренувати модель (`train_and_push.py`) на свіжіших даних, оцінити canary, промоутнути за стандартною процедурою вище.
4. Якщо потрібно негайно — rollback на попередню стабільну версію (`rollback_model.py`), доки не буде готова нова.

## Як видалити всю інфраструктуру

Порядок зворотний до розгортання (спочатку залежне, потім базове):
```bash
cd terraform/argocd && terraform destroy
cd ../eks && terraform destroy
cd ../vpc && terraform destroy
```
Після кожної команди підтвердіть `yes`. Перевірка, що нічого не залишилось:
```bash
aws eks list-clusters --region us-east-1 --profile goit-terraform
aws ec2 describe-instances --region us-east-1 --profile goit-terraform \
  --filters "Name=instance-state-name,Values=running,pending" \
  --query "Reservations[].Instances[].InstanceId"
```
Обидві команди мають повернути порожній результат.
