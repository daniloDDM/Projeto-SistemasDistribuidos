FROM python:3.13.7-alpine3.21

WORKDIR /app

RUN pip install pyzmq

COPY ./cliente.py .

CMD ["python", "cliente.py"]
