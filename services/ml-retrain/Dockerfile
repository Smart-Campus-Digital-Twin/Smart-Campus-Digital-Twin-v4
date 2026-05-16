# syntax=docker/dockerfile:1.7
# Stage 0: borrow Spark 4.1.1 from the cluster image (already cached locally)
FROM apache/spark:4.1.1 AS spark-dist

FROM apache/airflow:2.9.3 AS runtime

USER root
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && ln -sfn "/usr/lib/jvm/java-17-openjdk-$(dpkg --print-architecture)" \
           /usr/lib/jvm/java-17-openjdk

# Copy Spark 4.1.1 from the cluster image — version-matched, no pip download needed
COPY --from=spark-dist /opt/spark /opt/spark

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk \
    SPARK_HOME=/opt/spark \
    PATH="/usr/lib/jvm/java-17-openjdk/bin:/opt/spark/bin:${PATH}" \
    PYTHONPATH=/opt/spark/python \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER airflow
COPY airflow/requirements.txt /tmp/requirements.txt

# uid=50000 matches the airflow user in apache/airflow image
RUN --mount=type=cache,target=/home/airflow/.cache/pip,uid=50000,gid=0 \
    pip install --upgrade pip setuptools wheel \
    && pip install apache-airflow-providers-common-sql \
    && pip install --no-deps apache-airflow-providers-apache-spark==4.10.0 \
    && pip install -r /tmp/requirements.txt
