from airflow.decorators import dag, task
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from utils import create_connection
import datetime as dt
import json
import os

# AIRFLOW
AIRFLOW_HOME = os.getenv('AIRFLOW_HOME')
CONFIG_PATH = AIRFLOW_HOME + '/config'
PLUGINS_PATH = AIRFLOW_HOME + '/plugins'
LOGS_PATH = AIRFLOW_HOME + '/logs'
# FLASK
FLASK_HOST = os.getenv('FLASK_HOST')
FLASK_PORT = os.getenv('FLASK_PORT')
# KAFKA
KAFKA_HOST = os.getenv('KAFKA_HOST')
KAFKA_PORT = os.getenv('KAFKA_PORT')
KAFKA_SERVER = f'{KAFKA_HOST}:{KAFKA_PORT}'
# SPARK
SPARK_HOST = os.getenv('SPARK_HOST')
SPARK_PORT = os.getenv('SPARK_PORT')
# HIVE
HIVE_HOST = os.getenv('HIVE_HOST')
HIVE_PORT = os.getenv('HIVE_PORT')
# HDFS
HDFS_HOST = os.getenv('HDFS_HOST')
HDFS_PORT = os.getenv('HDFS_PORT')

with open(f'{CONFIG_PATH}/dags.json', 'r') as file:
  config = json.loads(file.read())

def create_dag(dag_id, entity, catalog, schema, schedule, kafka_topic):

  @dag(dag_id, schedule=schedule, start_date=dt.datetime(2024, 1, 1), catchup=False)
  def consume_stream():

    @task(task_id='spark_conn', retries=1)
    def use_create_connection(host, port, conn_type, conn_id):
      return create_connection(host, port, conn_type, conn_id)
    
    spark_conn_id = use_create_connection(SPARK_HOST, SPARK_PORT, 'spark', 'spark')

    args = [
      {
        'kafka_topic': kafka_topic,
        'kafka_server': KAFKA_SERVER,
        'catalog': catalog,
        'database': schema,
        'table': entity,
        'symbol': f'{entity}-USD'.upper(),
        'stream_checkpoint_path': f'opt/spark/checkpoints/{entity}'
      }
    ]

    spark_job = SparkSubmitOperator(
      task_id = f'consume_stream_{entity}',
      conn_id = 'spark',
      application=f'{CONFIG_PATH}/spark_jobs/consume_stream_job.py',
      py_files=f'{CONFIG_PATH}/utils/crypto_loader.py',
      application_args=[str(arg) for arg in args],
      conf={
        'spark.sql.extensions': 'org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions',
        'spark.master': f'spark://{SPARK_HOST}:{SPARK_PORT}',
        'spark.sql.catalog.iceberg': 'org.apache.iceberg.spark.SparkCatalog',
        'spark.sql.catalog.iceberg.type': 'hive',
        'spark.sql.catalog.iceberg.uri': f'thrift://{HIVE_HOST}:{HIVE_PORT}',
        'spark.sql.catalog.iceberg.warehouse': f'hdfs://{HDFS_HOST}:{HDFS_PORT}/iceberg'
      },
      packages="org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,org.apache.spark:spark-sql-kafka-0-10_2.12:3.1.2",
    )

    spark_conn_id >> spark_job

  consume_stream()


for entity in config:
  
  dag_id = f'consume_stream_{entity}'

  globals()[dag_id] = create_dag(
    dag_id, 
    entity, 
    config[entity]['catalog'],
    config[entity]['schema'],
    config[entity]['schedule'],
    config[entity]['kafka_topic']
  )