FROM dhi.io/python:3.14.6-alpine3.24-dev AS build

RUN apk add --no-cache git

WORKDIR /app

COPY requirements.txt .

RUN python -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM dhi.io/python:3.14.6-alpine3.24

WORKDIR /app

COPY --from=build /app/venv /app/venv

COPY --chown=nonroot:nonroot . .

USER nonroot

COPY --from=build --chown=nonroot:nonroot /app /app

ENV PATH="/app/venv/bin:$PATH"

CMD ["ddtrace-run", "python", "bot.py"]
