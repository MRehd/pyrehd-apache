import numpy as np
import pandas as pd
import pyspark.pandas as ps
import pyspark.sql.functions as F
from pyspark.sql.window import Window

def split_sequence(sequence, n_lookback, n_forecast):
  X = []
  Y = []

  for i in range(n_lookback, len(sequence) - n_forecast + 1):
      X.append(sequence[i - n_lookback: i])
      Y.append(sequence[i: i + n_forecast])

  X = np.array(X)
  Y = np.array(Y)

  return X, Y

def create_classificaiton_sequences(dataframe, sequence_length, features, target):
    """
    Transforms a DataFrame into sequences of 60 timesteps for each feature and the corresponding target variable.

    Parameters:
    - dataframe: Pandas DataFrame containing the columns 'x1', 'x2', 'x3', 'x4', 'x5', and 'y'.
    - sequence_length: The length of the sequence for model input.

    Returns:
    - X: NumPy array of shape (n_sequences, sequence_length, 5) containing input features.
    - y: NumPy array of shape (n_sequences,) containing the target variable.
    """
    X, y = [], []
    data = dataframe[features].values
    labels = dataframe[target].values
    
    for i in range(len(data) - sequence_length):
        X.append(data[i:i+sequence_length])
        y.append(labels[i+sequence_length-1])
    
    return np.array(X), np.array(y)

def create_sequences(data, look_back, predict_forward, target_feature_index=-1):
  """
  Create sequences of look_back length as input and predict_forward length as output.
  
  Parameters:
  - data: NumPy array of shape (num_samples, num_features).
  - look_back: Number of time steps to look back for input sequences.
  - predict_forward: Number of time steps to predict forward for output sequences.
  - target_feature_index: Index of the target feature in the data (default is 3 for 'Close').
  
  Returns:
  - X: Input sequences of shape (num_sequences, look_back, num_features).
  - y: Output sequences of shape (num_sequences, predict_forward).
  """
  X, y = [], []
  for i in range(len(data) - look_back - predict_forward + 1):
      X.append(data[i:(i + look_back)])
      y.append(data[(i + look_back):(i + look_back + predict_forward), target_feature_index])
  return np.array(X), np.array(y)

def split_multivariate_sequences(sequences, n_steps_in, n_steps_out):
  X, y = list(), list()
  for i in range(len(sequences)):
      # find the end of this pattern
      end_ix = i + n_steps_in
      out_end_ix = end_ix + n_steps_out-1
      # check if we are beyond the dataset
      if out_end_ix > len(sequences):
          break
      # gather input and output parts of the pattern
      seq_x, seq_y = sequences[i:end_ix, :-1], sequences[end_ix-1:out_end_ix, -1]
      X.append(seq_x)
      y.append(seq_y)
  return np.array(X), np.array(y)

def series_to_supervised_full_sequence(data, n_in=1, n_out=1, dropnan=True):
	"""
	Frame a time series as a supervised learning dataset.
	Arguments:
		data: Sequence of observations as a list or NumPy array.
		n_in: Number of lag observations as input (X).
		n_out: Number of observations as output (y).
		dropnan: Boolean whether or not to drop rows with NaN values.
	Returns:
		Pandas DataFrame of series framed for supervised learning.
	"""
	n_vars = 1 if type(data) is list else data.shape[1]
	df = pd.DataFrame(data)
	cols, names = list(), list()
	# input sequence (t-n, ... t-1)
	for i in range(n_in, 0, -1):
		cols.append(df.shift(i))
		names += [('var%d(t-%d)' % (j+1, i)) for j in range(n_vars)]
	# forecast sequence (t, t+1, ... t+n)
	for i in range(0, n_out):
		cols.append(df.shift(-i))
		if i == 0:
			names += [('var%d(t)' % (j+1)) for j in range(n_vars)]
		else:
			names += [('var%d(t+%d)' % (j+1, i)) for j in range(n_vars)]
	# put it all together
	agg = pd.concat(cols, axis=1)
	agg.columns = names
	# drop rows with NaN values
	if dropnan:
		agg.dropna(inplace=True)
	return agg

def series_to_supervised(data, n_in=1, n_out=1, dropnan=True):
    cols, names = list(), list()
    # Input sequence (t-n, ... t-1)
    for i in range(n_in, 0, -1):
        cols.append(data.shift(i))
        names += [('%s(t-%d)' % (col, i)) for col in data.columns]
    # Current timestep (t=0)
    cols.append(data)
    names += [('%s(t)' % (col)) for col in data.columns]
    # Target timestep (t=lag)
    cols.append(data.shift(-n_out))
    names += [('%s(t+%d)' % (col, n_out)) for col in data.columns]
    # Put it all together
    agg = pd.concat(cols, axis=1)
    agg.columns = names
    # Drop rows with NaN values
    if dropnan:
        agg.dropna(inplace=True)
    return agg

def fill_pd_missing_dates_backfill(df, date_col='ds', freq='D'):
    """
    Fills missing dates in a DataFrame and backfills missing values.

    Parameters:
    - df: pandas DataFrame with the time series data.
    - date_col: Name of the column in df that contains the datetime values.
    - value_col: Name of the column in df that contains the values to backfill.
    - freq: Frequency string to define the datetime range; 'D' for daily is the default.

    Returns:
    - DataFrame with no missing dates and backfilled values.
    """
    # Ensure 'ds' is a datetime type
    df[date_col] = pd.to_datetime(df[date_col])

    # Create a complete date range
    start_date, end_date = df[date_col].min(), df[date_col].max()
    complete_date_range = pd.date_range(start=start_date, end=end_date, freq=freq)

    # Reindex the DataFrame using the complete date range, backfilling missing 'y' values
    df.set_index(date_col, inplace=True)
    df = df.reindex(complete_date_range, method='backfill').rename_axis(date_col).reset_index()

    # Optionally, forward fill the first missing values if any, since backfill doesn't handle initial NaNs
    for col in df.columns:
        df[col] = df[col].fillna(method='ffill')

    return df

def fill_ps_missing_dates_backfill_pyspark(df, date_col='ds', value_col='y', freq='D'):
    """
    Fills missing dates in a PySpark Pandas DataFrame and backfills missing values.

    Parameters:
    - df: PySpark Pandas DataFrame with the time series data.
    - date_col: Name of the column in df that contains the datetime values.
    - value_col: Name of the column in df that contains the values to backfill.
    - freq: Frequency string to define the datetime range; 'D' for daily is the default.

    Returns:
    - DataFrame with no missing dates and backfilled values.
    """
    # Ensure 'ds' is a datetime type
    df[date_col] = ps.to_datetime(df[date_col])

    # Find the date range
    min_date, max_date = df[date_col].min(), df[date_col].max()
    date_range = ps.date_range(start=min_date, end=max_date, freq=freq)

    # Create a DataFrame from the complete date range
    date_df = ps.DataFrame(date_range, columns=[date_col])
    
    # Merge the original DataFrame with the date DataFrame
    df = date_df.merge(df, on=date_col, how='left')

    # Sort by date to ensure backfill works correctly
    df = df.sort_values(by=date_col)

    # Backfill missing 'y' values
    df[value_col] = df[value_col].fillna(method='backfill')
    
    # Optionally, forward fill to handle initial NaNs
    df[value_col] = df[value_col].fillna(method='ffill')

    return df

def fill_spark_missing_dates_backfill_pyspark(df, spark, date_col='ds', value_col='y', freq='D'):
    """
    Fills missing dates in a PySpark DataFrame and backfills missing values.

    Parameters:
    - df: PySpark DataFrame with the time series data.
    - spark: Spark session instance.
    - date_col: Name of the column in df that contains the datetime values.
    - value_col: Name of the column in df that contains the values to backfill.
    - freq: Frequency string to define the datetime range; 'D' for daily is the default. Note: This implementation assumes daily frequency.

    Returns:
    - DataFrame with no missing dates and backfilled values.
    """
    
    # Ensure 'ds' is a datetime type
    df = df.withColumn(date_col, F.to_date(df[date_col]))

    # Generate a date range
    min_date, max_date = df.select(F.min(date_col), F.max(date_col)).first()
    date_range = [x.date() for x in pd.date_range(start=min_date, end=max_date, freq=freq)]
    
    # Create a DataFrame from the date range
    date_df = spark.createDataFrame([(d,) for d in date_range], [date_col])
    
    # Join the original DataFrame with the date range DataFrame
    df = date_df.join(df, on=date_col, how='left_outer')
    
    # Backfill missing 'y' values
    # Window specification for ordering by date
    windowSpec = Window.orderBy(date_col).rowsBetween(Window.unboundedPreceding, 0)
    df = df.withColumn(value_col, F.last(df[value_col], ignorenulls=True).over(windowSpec))

    return df