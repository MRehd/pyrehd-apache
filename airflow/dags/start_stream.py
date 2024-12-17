from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.providers.http.hooks.http import HttpHook
from airflow.exceptions import AirflowException
from utils import create_connection
from trino.dbapi import connect
import datetime as dt
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
# START TIMESTAMPS
MIN_TIMESTAMP = {
  'btc': '2015-07-20 21:37:00',
  'eth': '2016-05-18 00:14:00'
}


with open(f'{CONFIG_PATH}/dags.json', 'r') as file:
  config = json.loads(file.read())

def create_dag(dag_id, entity, catalog, schema, schedule, kafka_topic, mode):

  @dag(dag_id, schedule=schedule, start_date=dt.datetime(2024, 1, 1), catchup=False)
  def start_stream():

    @task(task_id='producer_conn', retries=1)
    def use_create_connection(host, port, conn_type, conn_id):
      return create_connection(host, port, conn_type, conn_id)
    
    @task(task_id=f'{entity}_get_max_timestamp', retries=1)
    def get_max_timestamp(host, port, catalog, schema, entity):

      context = get_current_context()
      task_instance = context['ti']
      
      conn = connect(
          host=host,
          port=port,
          user='trino',
          catalog=catalog,
          schema=schema
      )
      cur = conn.cursor()
      cur.execute(f'SELECT max(Timestamp) FROM {entity}')
      last_timestamp = cur.fetchone()[0]
      return last_timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_timestamp else MIN_TIMESTAMP[entity]

    @task(task_id=f'stream_{entity}', retries=1)
    def stream(kafka_server, kafka_topic, entity, conn_id, start_time):

      context = get_current_context()
      task_instance = context['ti']
      
      http_hook = HttpHook(method='POST', http_conn_id=conn_id)

      headers = {
        'Content-Type': 'application/json'
      }

      data = {
        'kafka_server': kafka_server,
        'kafka_topic': kafka_topic,
        'symbol': f'{entity}-USD'.upper(),
        'start_time': start_time,
        'mode': mode
      }

      task_instance.xcom_push(key='params', value=data)

      response = http_hook.run(f'start-stream', data=json.dumps(data), headers=headers)

      if response.status_code != 200:
        raise AirflowException(f"Failed with status: {response.status_code}")
      
      return response.status_code

    stream(
      KAFKA_SERVER,
      kafka_topic,
      entity,
      use_create_connection(FLASK_HOST, FLASK_PORT, 'http', 'producer'), 
      get_max_timestamp(TRINO_HOST, TRINO_PORT, catalog, schema, entity)
    )

  start_stream()


for entity in config:
  
  dag_id = f'start_stream_{entity}'

  globals()[dag_id] = create_dag(
    dag_id, 
    entity, 
    config[entity]['catalog'], 
    config[entity]['schema'], 
    config[entity]['schedule'],
    config[entity]['kafka_topic'],
    config[entity]['mode']
  )