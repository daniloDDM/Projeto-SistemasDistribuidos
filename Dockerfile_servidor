FROM python:3.13.7-alpine3.21

WORKDIR /app

RUN pip install pyzmq

COPY ./servidor.py .

CMD ["python", "servidor.py"]
