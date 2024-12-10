from crypto_loader import CryptoLoader
from pyspark.sql import SparkSession
from pyspark import SparkConf, SparkContext
import sys


def consume_stream():
	spark = SparkSession(SparkContext().getOrCreate())
     
	args = sys.argv[1]
	params = eval(args)

	cl = CryptoLoader(
		spark,
		kafka_topic=params['kafka_topic'],
		kafka_server=params['kafka_server'],
		catalog=params['catalog'],
		database=params['database'],
		table=params['table'],
		symbol=params['symbol'],
		stream_checkpoint_path=params['stream_checkpoint_path']
	)

	cl.read_stream()

if __name__ == "__main__":
  consume_stream()