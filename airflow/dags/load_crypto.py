from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from zeppelin_operator import ZeppelinOperator
from airflow.hooks.base import BaseHook
from airflow import settings
from airflow.models import Connection
import datetime as dt
import logging
import os

AIRFLOW_HOME = os.getenv('AIRFLOW_HOME')
CONFIG_PATH = AIRFLOW_HOME + '/config'
HOST = '127.0.0.1'
PORT = 8084

@dag('load_crypto', schedule=None, start_date=dt.datetime(2024, 1, 1), catchup=False)
def load_crypto():

  @task(task_id='zeppelin-conn', retries=3)
  def create_http_connection(host, port):

    context = get_current_context()
    task_instance = context['ti']
    task_instance.xcom_push(key='host', value=host)
    task_instance.xcom_push(key='port', value=port)

    conn_id = 'zeppelin'

    try:
      conn = BaseHook.get_connection(conn_id)
      logging.info(f'Connection with ID {conn.id} already exists!')
    except:
      conn = Connection(
        conn_id=conn_id,
        conn_type='http',
        host=f'http://{host}:{port}/api/notebook/job/',
      )

      session = settings.Session()
      session.add(conn)
      session.commit()
      logging.info(f'Connection {conn_id} created successfully!')

    return conn.conn_id
  
  zepp_conn = create_http_connection(HOST, PORT)

  load_btc = ZeppelinOperator(
    task_id = 'load-btc',
    notebook_id='2KEH4HSWS',
    input={
      'coin': 'btc',
      'catalog': 'iceberg',
      'namespace': 'crypto',
      'table': 'btc'
    },
    conn_id=zepp_conn #f"{{ task_instance.xcom_pull(task_id='zeppelin, key=''conn_id) }}",
  )

  load_eth = ZeppelinOperator(
    task_id = 'load-eth',
    notebook_id='2KFZF5G34',
    input={
      'coin': 'eth',
      'catalog': 'iceberg',
      'namespace': 'crypto',
      'table': 'eth'
    },
    conn_id=zepp_conn,
  )

  zepp_conn >> [load_btc, load_eth]

load_crypto()