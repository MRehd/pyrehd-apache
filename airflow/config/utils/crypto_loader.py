from pyspark.sql.types import StructType, StructField, TimestampType, FloatType
import pyspark.sql.functions as f
import requests as r
from datetime import datetime, timedelta
import logging

class CryptoLoader:

  format_str = '%Y-%m-%d %H:%M:%S'
  schema = StructType([
    StructField('Timestamp', TimestampType(), True),
    StructField('Low', FloatType(), True),
    StructField('High', FloatType(), True),
    StructField('Open', FloatType(), True),
    StructField('Close', FloatType(), True),
    StructField('Volume', FloatType(), True)
  ])
  
  def __init__(
    self,
    spark,
    kafka_topic: str = None,
    kafka_server: str = None,
    start_time: str = None,
    end_time: str = None,
    catalog: str = '',
    database: str = '',
    table: str = '',
    granularity: int = 60,
    symbol: str = 'BTC-USD',
    window: int = 5,
    treshold: int = 10,
    buffer: int = 60,
    use_spark_sql: bool = True,
    initialize_iceberg_table: bool=True,
    stream_checkpoint_path: str=None
  ):
    self.spark = spark
    self.kafka_topic = kafka_topic
    self.kafka_server = kafka_server
    self.catalog = catalog
    self.database = database
    self.table = table
    self.iceberg_table = f'{self.catalog}.{self.database}.{self.table}'
    self.granularity = granularity
    self.symbol = symbol
    self.window = window
    self.use_spark_sql = use_spark_sql
    self.initialize_iceberg_table = initialize_iceberg_table
    self.stream_checkpoint_path = stream_checkpoint_path

    if self.initialize_iceberg_table:

      if self.use_spark_sql:
        self.spark.sql(f'USE {self.catalog};')
        self.spark.sql(f'CREATE NAMESPACE IF NOT EXISTS {self.catalog}.{self.database};')
        self.spark.sql(f'''CREATE TABLE IF NOT EXISTS {self.iceberg_table} (
                            Timestamp TIMESTAMP,
                            Low FLOAT,
                            High FLOAT,
                            Open FLOAT,
                            Close FLOAT,
                            Volume FLOAT
                        ) USING iceberg
                          PARTITIONED BY (
                            year(Timestamp)
                          );
                      '''
        )

      # if not using the catalog (which has a default location and simplifies things), you can write the iceberg table to hdfs by specifying the absolute path
      # then the table can be referenced by the catalog by adding the location clause to the sql query:
      # LOCATION 'hdfs://hdfs-namenode:9000/iceberg/crypto/btc'

      else:

        empty_df = spark.createDataFrame([], self.schema)
        table_exists = spark.catalog.tableExists(self.iceberg_table)

        if not table_exists:
          empty_df.writeTo(self.iceberg_table).using("iceberg").partitionedBy(f.year(f.col('Timestamp'))).create()
          print("Table created successfully!")
        else:
          print("Table already exists. Skipping creation.")

    if not start_time:
      self.start_time = self.get_latest_timestamp()
    else:
      self.start_time = start_time
    if not end_time:
      self.end_time = datetime.utcnow().strftime(self.format_str)
    else:
      self.end_time = end_time
    self.treshold = treshold
    self.buffer = buffer

    if self.window > 5:
      raise ValueError('Window parameter should be 5 hours or less.')

    print(f'Starting from: {self.start_time}')

  def _get_data(self, start_time, end_time):
    url = f'https://api.exchange.coinbase.com/products/{self.symbol}/candles?granularity={self.granularity}&start={start_time}&end={end_time}'
    return r.get(url).json()
  
  def _break_time_range(self, start_time, end_time):
    start = datetime.strptime(start_time, self.format_str)
    end = datetime.strptime(end_time, self.format_str)
    intervals = []

    while start < end:
      current_end = start + timedelta(hours=self.window)
      if current_end > end:
        current_end = end
      intervals.append((start.strftime(self.format_str), current_end.strftime(self.format_str)))
      start = current_end
    
    return intervals
  
  def _transform_data(self, data):
    return dict(
      [
        (
          col.name,
          datetime.utcfromtimestamp(val)
        )
        if col.name == 'Timestamp' else (col.name, float(val)) for col, val in zip(self.schema, data)
      ]
    )
  
  def recompact_partition(self, partitions, partition_name, repartition_size):
    for partition in partitions:
      df = self.spark.read.format("iceberg").load(self.iceberg_table).where(f"{partition_name} = '{partition}'")
      df_repartitioned = df.repartition(repartition_size)
      df_repartitioned.write.format("iceberg").mode("overwrite").option("replaceWhere", f"{partition_name}  = '{partition}'").save(self.iceberg_table)
      print(f"Compacted {partition_name} {partition}")
    return
  
  def get_latest_timestamp(self):
    if self.spark.catalog.tableExists(self.iceberg_table):
      max_timestamp = self.spark.read.format('iceberg').load(self.iceberg_table).select(f.max(f.col('Timestamp'))).collect()[0][0]
      if not max_timestamp:
        max_timestamp = '2014-01-01 00:00:00'
      else:
        max_timestamp = max_timestamp.strftime('%Y-%m-%d %H:%M:%S')
    else:
      max_timestamp = '2014-01-01 00:00:00'
    return max_timestamp

  def batch_update_ice_table(self):

    intervals = self._break_time_range(self.start_time, self.end_time)

    batch = []
    limit = 100000
    for interval_i, interval in enumerate(intervals):
      data = self._get_data(interval[0], interval[1])

      for i in range(len(data)):
        batch.append(self._transform_data(data[i]))

      if len(batch) >= limit or interval_i+1 == len(intervals):

        interval_df = self.spark.createDataFrame(batch, self.schema) \
          .sort('Timestamp', ascending=[True]) \
          .withColumn('Symbol', f.lit(self.symbol)) \
          .withColumn('Year', f.date_format(f.col('Timestamp'), 'yyyy').cast('string')) \
          .select(*self.schema.fieldNames())

        interval_df.write.mode('append').format('iceberg').save(self.iceberg_table) #.toTable(self.iceberg_table)
        print(f'Loaded {len(batch)} rows')

        batch = []
        self.start_time = interval[1]

  def read_stream(self):

    def merge_strat(batch_df, batch_id):
      temp_view = f"{self.table}_updates"
      batch_df.createOrReplaceGlobalTempView(temp_view)
      self.spark.sql(f"""
          MERGE INTO {self.iceberg_table} AS target
          USING global_temp.{temp_view} AS source
          ON target.Timestamp = source.Timestamp
          WHEN MATCHED THEN
            UPDATE SET *
          WHEN NOT MATCHED THEN
            INSERT *
        """
      )
    
    stream = self.spark \
      .readStream \
      .format('kafka') \
      .option('kafka.bootstrap.servers', self.kafka_server) \
      .option('subscribe', self.kafka_topic) \
      .option("startingOffsets", "earliest") \
      .load()
    
    parsed_stream = stream.select(f.from_json(f.decode(f.col("value"), 'utf-8').cast("string"), self.schema).alias("data"))
    transformed_stream = parsed_stream.select('data.*').dropDuplicates(['Timestamp'])

    iceberg_df = transformed_stream.writeStream \
      .format("iceberg") \
      .outputMode("append") \
      .trigger(processingTime='20 seconds') \
      .option("fanout-enabled", "true") \
      .option("checkpointLocation", self.stream_checkpoint_path) \
      .foreachBatch(merge_strat) \
      .start()
    
    try:
      iceberg_df.awaitTermination()
    except Exception as e:
      logging.error(f"Error in stream: {e}")

  def read_batch_stream(self):

    batch_stream = self.spark \
      .read \
      .format("kafka") \
      .option("kafka.bootstrap.servers", self.kafka_server) \
      .option("subscribe", self.kafka_topic) \
      .load() \
      .select(f.from_json(f.col("value").cast("string"), self.schema).alias("data")) \
      .select(*[f'data.{col}' for col in self.schema.fieldNames()])

    batch_stream = batch_stream \
      .sort('Timestamp', ascending=[True]) \
      .withColumn('Symbol', f.lit(self.symbol)) \
      .withColumn('Year', f.date_format(f.col('Timestamp'), 'yyyy').cast('string')) \
      .select(*self.schema.fieldNames())

    batch_stream.write.mode('append').format('iceberg').save(self.iceberg_table)
    print(f'Loaded {batch_stream.count()} rows')