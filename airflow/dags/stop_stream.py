from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.providers.http.hooks.http import HttpHook
from airflow.exceptions import AirflowException
from utils import create_connection
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

with open(f'{CONFIG_PATH}/dags.json', 'r') as file:
  config = json.loads(file.read())

def create_dag(dag_id, entity, schedule, kafka_topic):

  @dag(dag_id, schedule=schedule, start_date=dt.datetime(2024, 1, 1), catchup=False)
  def stop_stream():

    @task(task_id='producer_conn', retries=1)
    def use_create_connection(host, port, conn_type, conn_id):
      return create_connection(host, port, conn_type, conn_id)
    
    @task(task_id=f'stop_stream_{entity}', retries=1)
    def stop(kafka_topic, conn_id):

      context = get_current_context()
      task_instance = context['ti']
      
      http_hook = HttpHook(method='POST', http_conn_id=conn_id)

      headers = {
        'Content-Type': 'application/json'
      }

      data = {
        'kafka_topic': kafka_topic,
      }

      response = http_hook.run(f'stop-stream', data=json.dumps(data), headers=headers)

      if response.status_code != 200:
        raise AirflowException(f"Failed with status: {response.status_code}")
      
      logging.info(f'Stream for topic {kafka_topic} has stopped!')
      
      return response.status_code

    stop(
      kafka_topic,
      use_create_connection(FLASK_HOST, FLASK_PORT, 'http', 'producer')
    )

  stop_stream()


for entity in config:
  
  dag_id = f'stop_stream_{entity}'

  globals()[dag_id] = create_dag(
    dag_id, 
    entity, 
    config[entity]['schedule'],
    config[entity]['kafka_topic'],
  )