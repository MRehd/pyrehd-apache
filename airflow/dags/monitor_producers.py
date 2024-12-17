from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.providers.http.hooks.http import HttpHook
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from airflow.models import Connection
from airflow import settings
import datetime as dt
import logging
import json
import os

# AIRFLOW
AIRFLOW_HOME = os.getenv('AIRFLOW_HOME')
CONFIG_PATH = AIRFLOW_HOME + '/config'
# FLASK
FLASK_HOST = os.getenv('FLASK_HOST')
FLASK_PORT = os.getenv('FLASK_PORT')
# KAFKA
KAFKA_HOST = os.getenv('KAFKA_HOST')
KAFKA_PORT = os.getenv('KAFKA_PORT')
KAFKA_SERVER = f'{KAFKA_HOST}:{KAFKA_PORT}'
# TRINO
TRINO_HOST = os.getenv('TRINO_HOST')
TRINO_PORT = os.getenv('TRINO_PORT')

with open(f'{CONFIG_PATH}/dags.json', 'r') as file:
  config = json.loads(file.read())

def create_dag(dag_id, entity, schedule, kafka_topic):

  @dag(dag_id, schedule=schedule, start_date=dt.datetime(2024, 1, 1), catchup=False)
  def monitor_stream():

    @task(task_id='producer_conn', retries=1)
    def create_http_connection(host, port):

      context = get_current_context()
      task_instance = context['ti']
      task_instance.xcom_push(key='host', value=host)
      task_instance.xcom_push(key='port', value=port)

      conn_id = 'producer'

      try:
        conn = BaseHook.get_connection(conn_id)
        logging.info(f'Connection with ID {conn.id} already exists!')
      except:
        conn = Connection(
          conn_id=conn_id,
          conn_type='http',
          host=f'http://{host}:{port}/',
        )

        session = settings.Session()
        session.add(conn)
        session.commit()
        logging.info(f'Connection {conn_id} created successfully!')

      return conn.conn_id
    
    @task(task_id=f'get_stream_status_{entity}', retries=1)
    def get_stream_status(conn_id, kafka_topic):
      
      http_hook = HttpHook(method='GET', http_conn_id=conn_id)
      response = http_hook.run(f'stream-status')
      status_code = response.status_code
      status = response.json()['status'].get(kafka_topic)

      if status_code != 200:
        raise AirflowException(f"Failed with status: {status_code}")
      
      if not status:
        raise AirflowException(f'Stream for {kafka_topic} is stopped!')

      return status

    get_stream_status(
      create_http_connection(FLASK_HOST, FLASK_PORT),
      kafka_topic
    )

  monitor_stream()


for entity in config:
  
  dag_id = f'monitor_producer_{entity}'

  globals()[dag_id] = create_dag(
    dag_id, 
    entity, 
    config[entity]['monitor_schedule'],
    config[entity]['kafka_topic']
  )