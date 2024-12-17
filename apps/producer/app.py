from flask import Flask, request, jsonify
from utils.producer import CryptoProducer
import threading
import logging

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

threads = {}
producers = {}
registry_lock = threading.Lock()

@app.route('/start-stream', methods=['POST'])
def start_stream():
	"""API endpoint to start a new stream."""
	params = request.get_json(force=True)
	kafka_topic = params.get('kafka_topic')

	if not kafka_topic:
		return jsonify({"error": "Missing 'kafka_topic' in request body."}), 400
	
	if kafka_topic not in producers:

		producer = CryptoProducer(
			kafka_server=params['kafka_server'],
			kafka_topic=kafka_topic,
			start_time=params['start_time'],
			symbol=params['symbol'],
			mode=params['mode']
		)
		producers[kafka_topic] = producer

		with registry_lock:
			if kafka_topic in threads:
				return jsonify({"error": f"Stream for topic '{kafka_topic}' is already running."}), 200

			# Create a new thread for the producer
			producer_thread = threading.Thread(
				target=producer.start, daemon=True
			)
			threads[kafka_topic] = producer_thread
			producer_thread.start()
			logging.info(f"Started thread for Kafka topic '{kafka_topic}'.")

		return jsonify({"message": f"Stream for topic '{kafka_topic}' started successfully."}), 200

@app.route('/stop-stream', methods=['POST'])
def stop_stream():
	"""API endpoint to stop a stream."""
	params = request.get_json(force=True)
	kafka_topic = params.get('kafka_topic')

	if not kafka_topic:
		return jsonify({"error": "Missing 'kafka_topic' in request body."}), 400

	with registry_lock:
		producer = producers.pop(kafka_topic, None)
		producer_thread = threads.pop(kafka_topic, None)

	if not producer or not producer_thread:
		return jsonify({"message": f"No active stream found for topic '{kafka_topic}'."}), 200

	try:
		# Stop the producer
		if producer:
			producer.stop()

		# Join the thread to ensure it finishes cleanly
		if producer_thread:
			producer_thread.join(timeout=5)
		logging.info(f"Stopped thread for Kafka topic '{kafka_topic}'.")
		return jsonify({"message": f"Stream for topic '{kafka_topic}' stopped successfully."}), 200
	except Exception as e:
		return jsonify({"error": f"Failed to stop stream for topic '{kafka_topic}': {str(e)}"}), 500


@app.route('/stream-status', methods=['GET'])
def stream_status():
	"""API endpoint to get the status of all streams."""
	with registry_lock:
		statuses = {topic: producer.status() for topic, producer in producers.items()}
		return jsonify({"status": statuses}), 200

if __name__ == '__main__':
  app.run(host="0.0.0.0", port=8087)