from flask import Flask, request, jsonify
from utils.producer import CryptoProducer
from threading import Lock
import logging

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

producers = {}
registry_lock = Lock() 

@app.route('/start-stream', methods=['POST'])
def start_stream():

	params = request.get_json(force=True)

	logging.info(params)
	
	producer = CryptoProducer(
		kafka_server = params['kafka_server'],
		kafka_topic = params['kafka_topic'],
		start_time = params['start_time'],
		symbol = params['symbol'],
		mode = params['mode']
	)

	try:
		producer.start()
		producers[params['kafka_topic']] = producer
		return jsonify({"message": "Stream started"}), 200
	except RuntimeError as e:
		return jsonify({"error": str(e)}), 400

@app.route('/stop-stream', methods=['POST'])
def stop_stream():
     
	params = request.get_json(force=True)

	with registry_lock:
            
		if params['kafka_topic'] not in producers:
			return jsonify({"error": f"No active stream found for topic '{params['kafka_topic']}'."}), 400

		producer = producers.pop(params['kafka_topic'])
            
		try:
			producer.stop()
			return jsonify({"message": "Stream stopped"}), 200
		except Exception as e:
			return jsonify({"error": str(e)}), 400

@app.route('/stream-status', methods=['GET'])
def stream_status():
	with registry_lock:
		statuses = {topic: producer.status() for topic, producer in producers.items()}
	return jsonify({"status": statuses}), 200

if __name__ == '__main__':
  app.run(host="0.0.0.0", port=8087)