# Автодеплой в Yandex Cloud через GitHub Actions

Этот файл описывает, как один раз настроить CI/CD, чтобы деплой в Yandex Cloud Serverless Containers происходил **автоматически при пуше в `main`**.

Файл пайплайна уже добавлен: `.github/workflows/deploy.yml`.

## 1. Что будет делать пайплайн

- На каждый `push` в ветку `main`:
  - собирает Docker-образ приложения (`linux/amd64`);
  - пушит образ в Yandex Container Registry (`duty-schedule-reg`);
  - создаёт / обновляет serverless-контейнер `duty-schedule-streamlit`;
  - деплоит новую ревизию и делает её публичной.

В результате приложение доступно по URL:

```text
https://<container-id>.containers.yandexcloud.net/
```

## 2. Разовая подготовка в Yandex Cloud

Все действия ниже выполняются **один раз**.

### 2.1. Сервисный аккаунт

```bash
YC_FOLDER_ID=<ID_каталога>   # можно посмотреть: yc config get folder-id

yc iam service-account create --name duty-schedule-ci

YC_SA_ID=$(yc iam service-account get --name duty-schedule-ci --format json | jq -r '.id')

yc resource-manager folder add-access-binding \
  --id "$YC_FOLDER_ID" \
  --service-account-id "$YC_SA_ID" \
  --role container-registry.admin

yc resource-manager folder add-access-binding \
  --id "$YC_FOLDER_ID" \
  --service-account-id "$YC_SA_ID" \
  --role serverless.containers.admin
```

### 2.2. Получить IDs облака и каталога

```bash
yc config get cloud-id      # YC_CLOUD_ID
yc config get folder-id     # YC_FOLDER_ID
```

Запиши эти два значения — они понадобятся в секретах GitHub.

### 2.3. OAuth-токен для CI

1. Перейди по ссылке:

   ```text
   https://oauth.yandex.ru/authorize?response_type=token&client_id=1a6990aa636648e9b2ef855fa7bec2fb
   ```

2. Войди под аккаунтом, у которого есть доступ к нужному облаку/каталогу.
3. Скопируй выданный OAuth-токен (строка вида `y0_...`).

**Не публикуй токен, не отправляй его в чат, храни только в секретах GitHub.**

## 3. Настройка секретов в GitHub

В репозитории GitHub:

1. Открой `Settings` → `Secrets and variables` → `Actions` → `New repository secret`.
2. Создай 4 секрета:

- `YC_OAUTH_TOKEN` — скопированный OAuth-токен.
- `YC_CLOUD_ID` — значение из `yc config get cloud-id`.
- `YC_FOLDER_ID` — значение из `yc config get folder-id`.
- `YC_SA_ID` — ID сервисного аккаунта `duty-schedule-ci`:

  ```bash
  yc iam service-account get --name duty-schedule-ci --format json | jq -r '.id'
  ```

## 4. Как это работает дальше

- При следующем пуше в ветку `main`:
  - GitHub Actions запустит workflow `Deploy to Yandex Cloud Serverless Container`.
  - В результате появится / обновится контейнер `duty-schedule-streamlit` в выбранном каталоге.

Посмотреть URL контейнера:

```bash
yc serverless container get duty-schedule-streamlit --format json | jq -r '.url'
```

Открой этот URL в браузере — это всегда будет актуальная версия приложения из ветки `main`.

