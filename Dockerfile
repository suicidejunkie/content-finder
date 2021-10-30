FROM python:3.10-slim-buster

WORKDIR /app

COPY ./requirements.txt .
COPY ./setup.py .

RUN python -m pip install -e .

COPY ./cytubebot ./cytubebot

COPY ./.env .

ENV PYTHONUNBUFFERED=1

CMD ["python", "cytubebot/main.py"]