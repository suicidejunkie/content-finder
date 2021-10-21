FROM python:3.9-slim-buster

WORKDIR /app

COPY ./requirements.txt .

RUN python -m pip install -r requirements.txt

COPY ./main.py .

COPY ./.env .

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]