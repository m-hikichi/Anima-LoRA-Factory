# syntax=docker/dockerfile:1.7
ARG PYTORCH_IMAGE=pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime
FROM ${PYTORCH_IMAGE}

ARG UPSTREAM_ARCHIVE=Anima-LoRA-Factory-v6.0.zip

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/build
COPY docker/ /opt/docker/
COPY ${UPSTREAM_ARCHIVE} /tmp/upstream.zip

RUN python /opt/docker/materialize.py \
      --archive /tmp/upstream.zip \
      --lock /opt/docker/upstream.lock.json \
      --output /opt/anima \
    && rm /tmp/upstream.zip

RUN python -m pip install --no-cache-dir -r /opt/anima/backend/requirements.txt \
    && cd /opt/anima/backend/sd-scripts \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

WORKDIR /opt/anima/backend
EXPOSE 8000

CMD ["python", "main.py"]

