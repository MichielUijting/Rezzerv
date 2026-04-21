FROM python:3.11-slim

WORKDIR /app

# Systeembinaries voor OCRmyPDF + runtime-libs voor image/OCR stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-nld \
    ghostscript \
    qpdf \
    pngquant \
    unpaper \
    fonts-noto-core \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Eerst basis tooling, dan PaddlePaddle CPU-wheel, daarna Python requirements
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY VERSION.txt ./VERSION.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
