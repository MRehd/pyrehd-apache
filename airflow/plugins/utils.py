from airflow.operators.python import get_current_context
from airflow.hooks.base import BaseHook
from airflow.models import Connection
from airflow import settings
import logging

def create_connection(host, port, conn_type, conn_id):

  context = get_current_context()
  task_instance = context['ti']
  task_instance.xcom_push(key='host', value=host)
  task_instance.xcom_push(key='port', value=port)

  try:
    conn = BaseHook.get_connection(conn_id)
    logging.info(f'Connection with ID {conn.conn_id} already exists!')
  except:
    conn = Connection(
      conn_id=conn_id,
      conn_type=conn_type,
      host=host,
      port=port
    )

    session = settings.Session()
    session.add(conn)
    session.commit()
    logging.info(f'Connection {conn_id} created successfully!')

  return conn.conn_id