# Threat Model

Односторінковий attack surface для MovieLens MLOps-платформи: 5 загроз і контролі, що їх знижують.

## 1. Підроблена/пошкоджена модель у MinIO (S3-сховищі артефактів)

**Загроза:** зловмисник (або баг) підміняє файл моделі в MinIO напряму, минаючи MLflow Registry. Inference-сервіс завантажує й обслуговує вже скомпрометовану модель, ніхто цього не помічає.

**Контроль:** SHA256 checksum обчислюється в момент реєстрації (`train_and_push.py`, тег `artifact_sha256` на версії моделі), і inference-сервіс перевіряє його **перед** завантаженням (`inference/app/model.py`) — при розбіжності відмовляється стартувати, а не мовчки обслуговує підмінений артефакт. Перевірено практично: підробка тегу викликає HTTP 500 замість завантаження.

## 2. Excessive resource consumption / DoS на inference-endpoint

**Загроза:** один клієнт (помилково чи навмисно) заливає `/predict`/`/recommend` запитами, вичерпуючи CPU/пам'ять подів і деградуючи сервіс для всіх користувачів.

**Контроль:** rate limiting на рівні застосунку (20 запитів/10с на IP, `inference/app/main.py`). **Відомий ліміт:** стан лічильника локальний для кожного поду (немає Redis чи shared store) — у production (10 реплік) ефективна межа масштабується з кількістю подів, а не є жорсткою кластерною межею. Прийнятний компроміс для навчального проєкту; для реального продакшену — Redis-backed rate limiter або rate-limit на Ingress/API Gateway.

## 3. Неавторизована зміна production через kubectl/Model Registry

**Загроза:** будь-хто з доступом до кластера видаляє/змінює production-ресурси або довільно переводить моделі в Production/видаляє версії з Registry, обходячи процес promotion.

**Контроль:** RBAC (`rbac/`) — група `mlops-engineer` має повний доступ лише в `staging`; у `production` — тільки read + `patch` на Deployments (саме стільки, скільки потрібно для `kubectl rollout restart` після promotion/rollback), без `delete`/`create`/доступу до Secrets. Група `viewer` — read-only, Secrets виключені явним переліком ресурсів (RBAC адитивний, тому wildcard `resources: ["*"]` для viewer навмисно не використовується). Перевірено через `kubectl auth can-i`.

## 4. Витік внутрішніх деталей через API-помилки

**Загроза:** невалідний або зловмисно сформований запит до `/predict`/`/recommend` повертає stack trace, шляхи файлів чи внутрішню структуру Pydantic-схеми — корисна розвідувальна інформація для атаки.

**Контроль:** кастомний exception handler для `RequestValidationError` повертає HTTP 400 із generic-повідомленням (`"invalid request body"`), деталі лише логуються структуровано у Loki, не повертаються клієнту. Аналогічно — будь-яке необроблене виключення в middleware повертає generic HTTP 500, а не traceback (`inference/app/main.py`).

## 5. Відсутність аудиту дій з Model Registry

**Загроза:** хтось (або зламаний CI) промоутить некоректну версію в Production або видаляє версію з Registry — і немає way дізнатись, хто, коли й що саме зробив, окрім самого MLflow UI (де історія обмежена і не централізована з рештою логів системи).

**Контроль:** усі зміни stage (`register_and_stage`, `promote_to_production`, `rollback_production`) пушаться як структуровані JSON-події напряму в Loki (`experiments/audit_log.py`), поруч із логами inference-сервісу — єдине місце для розслідування інцидентів. Перевірено практично: подія `register_and_stage` знайдена через Loki query API.

## Оновлення: креденшели MinIO/Postgres/MLflow

Раніше в цьому розділі була описана загроза "хардкоджені креденшели MinIO/Postgres у git" — виправлено: реальні паролі тепер живуть лише в Kubernetes Secret (`minio-credentials`, `postgres-credentials`), створюваних вручну під час bootstrap (`kubectl create secret`, README.md, Фаза 2.5) і **ніколи не потрапляють у git**. Helm-values посилаються на них через `existingSecret` (MinIO, Postgres, MLflow-чарти) і `secretKeyRef` (inference-деплойменти). Залишковий ризик — секрети досі не ротуються автоматично і не керуються зовнішнім secret-manager (Vault/External Secrets Operator); прийнятний компроміс для навчального проєкту з коротким життєвим циклом інфраструктури (~24 год), задокументовано в `ADR.md`.
