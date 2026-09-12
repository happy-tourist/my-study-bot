FROM python:3.13-slim

# Устанавливаем корневые сертификаты (чтобы Python доверял SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала копируем requirements и ставим зависимости — так Docker кеширует слой
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Создаём папку для данных (на случай, если volume ещё не смонтирован)
RUN mkdir -p /app/data

CMD ["python", "main.py"]
