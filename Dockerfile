# Dockerfile
FROM apache/airflow:3.0.2

# ---add sops + age---------
ARG SOPS_VERSION=3.13.1
ARG SOPS_SHA256=620a9d7e3352ababeca6908cea24a6e8b14ce89a448ddbd3f94f1ef3398f470a

USER root
RUN apt-get update && apt-get install -y --no-install-recommends age curl \
    && curl -fsSL -o /usr/local/bin/sops \
        https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.linux.amd64 \
    && chmod +x /usr/local/bin/sops \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.0.2/constraints-3.12.txt"