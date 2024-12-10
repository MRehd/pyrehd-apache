from airflow.models.baseoperator import BaseOperator
from airflow.providers.http.hooks.http import HttpHook
from airflow.utils.decorators import apply_defaults
from airflow.exceptions import AirflowException
from typing import Sequence
import logging
import json
import time

class ZeppelinOperator(BaseOperator):

	template_fields: Sequence[str] = ['conn_id']

	@apply_defaults
	def __init__(
		self,
		notebook_id: str,
		conn_id: str,
		input: object,
		*args,
		**kwargs
	) -> None:
		self.notebook_id = notebook_id
		self.input = json.dumps({'params': input})
		self.conn_id = conn_id
		super().__init__(*args, **kwargs)

	def execute(self, context):
		# Initialize the HttpHook
		http_hook = HttpHook(method='POST', http_conn_id=self.conn_id)

		# Make the HTTP request
		response = http_hook.run(self.notebook_id, data=self.input)

		# Check the response status
		if response.status_code != 200:
				logging.error(f"Request failed: {response.status_code}")
				raise AirflowException(f"Failed with status: {response.status_code}")
		else:
			time.sleep(15)
			http_hook_get = HttpHook(method='GET', http_conn_id=self.conn_id)
		
			while True:

				get_response = http_hook_get.run(self.notebook_id, data=self.input)
				status_code = get_response.status_code
				response_body = get_response.json()['body']
				if status_code == 200:
					is_running = response_body['isRunning']
					
					if is_running:
						logging.info(f'Notebook is still running...')
						logging.info(get_response.json())
						time.sleep(5)

					elif 'ERROR' in [cell['status'] for cell in response_body['paragraphs']]:
						raise AirflowException(f'Notebook failed: {response_body}')
					else:
						logging.info(f'Notebook finished successfully! Response: {response_body}')
						break
				else:
					raise AirflowException(f'Notebook failed: {get_response.text}')

		return