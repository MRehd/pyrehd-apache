from datetime import datetime, timedelta
import requests as r
import asyncio
import threading
import aiokafka
import kafka
import logging
import json
import time

class CryptoProducer:

  format_str = '%Y-%m-%d %H:%M:%S'
  schema = ['Timestamp', 'Low', 'High', 'Open', 'Close', 'Volume']
  
  def __init__(
    self,
    kafka_topic: str = None,
    kafka_server: str = None,
    start_time: str = None,
    end_time: str = None,
    granularity: int = 60,
    symbol: str = None,
    window: int = 5,
    buffer: int = 60,
    mode: str = 'sync',
  ):
    self.kafka_topic = kafka_topic
    self.kafka_server = kafka_server
    self.granularity = granularity
    self.symbol = symbol
    self.window = window
    self.start_time = start_time
    self.end_time = end_time
    self.buffer = buffer
    self.mode = mode

    self.is_running = False
    self.thread = None

    if not end_time:
      self.end_time = datetime.utcnow().strftime(self.format_str)

    self.producer = kafka.KafkaProducer(
      bootstrap_servers=self.kafka_server, 
      value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
      key_serializer=lambda k: k.encode('utf-8')
    )

    self.aio_producer = None

    self.mode_mapping = {
      'sync': self._feed_stream,
      'async': self._async_feed_stream,
      'aio_async': self._async_feed_stream_aiokafka
    }

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
          col,
          datetime.utcfromtimestamp(val)
        )
        if col == 'Timestamp' else (col, float(val)) for col, val in zip(self.schema, data)
      ]
    )
  
  def _on_send_success(self, record_metadata):
    logging.info(record_metadata.topic)
    logging.info(record_metadata.partition)
    logging.info(record_metadata.offset)

  def _on_send_error(self, excp):
    logging.error('Error sending message', exc_info=excp)

  def _feed_stream(self):

    self.is_running = True
    last = None
    
    try:
      while self.is_running:
        # Set data interval
        intervals = self._break_time_range(self.start_time, self.end_time)

        # Get data for the interval
        for interval in intervals:
          data = self._get_data(interval[0], interval[1])
          data = sorted(data, key=lambda x: x[0])
          for row in data:
            event = self._transform_data(row)
            event_timestamp = event['Timestamp'].strftime(self.format_str)
            if not last or event_timestamp > self.start_time:
              self.producer.send(self.kafka_topic, key=event_timestamp, value=event).add_callback(self._on_send_success).add_errback(self._on_send_error)
              last = event_timestamp
              self.producer.flush()
        
        self.start_time = last

        # Wait for more data to be available
        time_diff = datetime.utcnow() - datetime.strptime(last, self.format_str)
        time_diff_sec = time_diff.total_seconds()

        if time_diff_sec < self.buffer:
          wait_time = self.buffer - time_diff_sec
          if wait_time > 0:
            time.sleep(wait_time)
          else:
            time.sleep(1)

        self.end_time = datetime.utcnow().strftime(self.format_str)
    except Exception as e:
      self.producer.close()
      raise RuntimeError(e)

  async def _async_feed_stream(self):

    self.is_running = True
    last = None
    
    try:

      while self.is_running:
        # Set data interval
        intervals = self._break_time_range(self.start_time, self.end_time)

        futures = []
        timestamps = []

        # Get data for the interval
        for interval in intervals:
          data = self._get_data(interval[0], interval[1])
          for row in data:
            event = self._transform_data(row)
            event_timestamp = event['Timestamp'].strftime(self.format_str)
            max_timestamp = max(timestamps) if len(timestamps) > 0 else last
            if not last or event_timestamp > max_timestamp:
              future = self.producer.send(self.kafka_topic, key=event_timestamp, value=event)
              future.add_callback(self._on_send_success)
              future.add_errback(self._on_send_error)
              futures.append(asyncio.get_event_loop().run_in_executor(None, future.get))
              timestamps.append(event_timestamp)

        last = max(timestamps) if len(timestamps) > 0 else last
        self.start_time = last

        await asyncio.gather(*futures)
        self.producer.flush()

        # Wait for more data to be available
        time_diff = datetime.utcnow() - datetime.strptime(last, self.format_str)
        time_diff_sec = time_diff.total_seconds()

        if time_diff_sec < self.buffer:
          wait_time = self.buffer - time_diff_sec
          if wait_time > 0:
            time.sleep(wait_time)
          else:
            time.sleep(1)

        self.end_time = datetime.utcnow().strftime(self.format_str)

    except Exception as e:
      self.producer.close()
      raise RuntimeError(e)
    
  async def _async_feed_stream_aiokafka(self):

    if not self.aio_producer:
      self.aio_producer = aiokafka.AIOKafkaProducer(
        bootstrap_servers=self.kafka_server, 
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8'),
        loop=asyncio.get_event_loop()
      )

    self.is_running = True
    last = None
    
    async with self.aio_producer:

      while self.is_running:
        # Set data interval
        intervals = self._break_time_range(self.start_time, self.end_time)

        futures = []
        timestamps = []

        # Get data for the interval
        for interval in intervals:
          data = self._get_data(interval[0], interval[1])
          for row in data:
            event = self._transform_data(row)
            event_timestamp = event['Timestamp'].strftime(self.format_str)
            max_timestamp = max(timestamps) if len(timestamps) > 0 else last
            if not last or event_timestamp > max_timestamp:
              future = self.aio_producer.send(self.kafka_topic, key=event_timestamp, value=event)
              futures.append(future)
              timestamps.append(event_timestamp)

        last = max(timestamps) if len(timestamps) > 0 else last
        self.start_time = last

        await asyncio.gather(*futures)
        await self.aio_producer.flush()

        # Wait for more data to be available
        time_diff = datetime.utcnow() - datetime.strptime(last, self.format_str)
        time_diff_sec = time_diff.total_seconds()

        if time_diff_sec < self.buffer:
          wait_time = self.buffer - time_diff_sec
          if wait_time > 0:
            time.sleep(wait_time)
          else:
            time.sleep(1)

        self.end_time = datetime.utcnow().strftime(self.format_str)

  def start(self):
    if self.thread and self.thread.is_alive():
      raise RuntimeError("Producer is already running.")

    self.thread = threading.Thread(target=self.mode_mapping[self.mode])
    self.thread.daemon = True
    self.thread.start()
    logging.info("Producer started.")

  def stop(self):
    if not self.is_running:
      logging.info("Producer is not running.")
      return
    self.is_running = False
    if self.thread:
      self.thread.join()
    logging.info("Producer stopped.")
    
  def status(self):
    return self.is_running