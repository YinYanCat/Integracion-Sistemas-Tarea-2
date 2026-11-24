FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py bd.py ./

ENV RECETA_DB_PATH=/data/receta.db

EXPOSE 8103

CMD ["python", "app.py"]
