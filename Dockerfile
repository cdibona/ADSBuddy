FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Deployed version, shown in the footer. Passed by docker-compose from
# $ADSBUDDY_GIT_SHA; defaults to "dev" for plain `docker build`. Kept last so
# changing it doesn't bust the pip/dependency layers above.
ARG ADSBUDDY_GIT_SHA=dev
ENV ADSBUDDY_GIT_SHA=${ADSBUDDY_GIT_SHA}
# Release version (e.g. 1.2.3), baked from the git tag by the release workflow;
# "dev" for local builds. Drives the "update available" check.
ARG ADSBUDDY_VERSION=dev
ENV ADSBUDDY_VERSION=${ADSBUDDY_VERSION}

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
