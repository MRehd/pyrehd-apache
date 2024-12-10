# Apache centered Data Platform on Docker
This is an ongoing project which explores the integration of various open source data components to provide a working (not suitable for production) conteinarized data platform, with both batch and streaming capabilities to pull data from the coinabse API. The platform can be started with docker-compose up (make sure to add your IP to nginx/nginx.conf). The platform is a bit computationally intense for local machines.

The implementation is not yet finished, so there are still bugs to fix, some incomplete functionalities and new features to be introduced. A diagram to display the architecture is also coming soon.

Summary of the resources:

- Apache Spark for data processing (batch and stream with spark structured streaming)

- Kafka for streaming

- Apache Airflow for orchestration of batch and streaming jobs (starting kafka producer (flask app) and consumer (spark cluster via spark-submit), and periodically monitoring the stream of data).

- Hadoop File System for storing the data in iceberg format

- Hive for metastore/catalogs management

- Apache Superset for data visualization

- Apache Zeppelin for data exploration through notebook interface

- Postgres instances for Apache Airflow, Hive Metastore and Apache Superset backend

- Trino as the query 

- NGINX for networking

# Upcoming

- MLFlow implementation and neural network backed forecasting

Some useful commands:

## list running containers
docker ps

## access container terminal
docker exec -it <container_id> bash

## copy files from container to local path, ex:
docker cp baba55c9b26f:/opt/zeppelin/conf/ /local/path

## Hive Metastore
docker exec -it hive-metastore /opt/hive/bin/beeline
!connect jdbc:hive2://hive-server:10000
(user: hive, password: hive)

## Access trino
docker exec -it trino trino
conn str: 
  trino://trino@trino:8080/iceberg (no password)
  trino://user:password@host:8080/iceberg

## Superset
username: admin
password: admin