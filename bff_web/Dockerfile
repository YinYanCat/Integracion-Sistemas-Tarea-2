FROM python:3.12-slim

WORKDIR /app

COPY bff_web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY contratos/stock.proto ./stock.proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stock.proto

COPY bff_web/ ./

ENV BFF_PORT=8090

EXPOSE 8090

CMD ["python", "app.py"]
