FROM python:3.11-slim

# Tizim uchun zarur bo'lgan ffmpeg va curl dasturlarini o'rnatamiz
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kodlarni ko'chirish
COPY . .

# Botni ishga tushirish (Render beradigan PORT ni avtomatik oladi)
CMD ["python", "main.py"]
