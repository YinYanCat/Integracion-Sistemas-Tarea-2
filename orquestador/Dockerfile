FROM python:3.12-slim

WORKDIR /app

COPY orquestador/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY contratos/stock.proto ./stock.proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stock.proto

COPY orquestador/ ./

ENV SAGA_DB_PATH=/data/saga.db

EXPOSE 8104

CMD ["python", "app.py"]
