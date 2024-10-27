from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, concat_ws, to_date, to_timestamp, date_format, when, explode, year, month, dayofmonth, hour, minute
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, ArrayType, TimestampType, IntegerType


# Create Spark session
spark = SparkSession.builder \
    .appName("StockDataKafkaStreaming") \
    .getOrCreate()

# Kafka parameters
kafka_bootstrap_servers = "10.0.0.10:9092,10.0.0.11:9092,10.0.0.12:9092"
kafka_topic = "StocksTopic"

# Google Cloud Storage bucket path for streaming output
gcs_bucket_name = "my-temp-bucket-123456"

# Checkpoint location in GCS
checkpoint_location = "gs://my-temp-bucket-123456/ٍStock_Checkpoint/"


# Define BigQuery table
project_id = "realtimepiplineproject"
dataset_id = "Stock_DWH"
table_id = "Stock_Data"

# Define schema for stock data
schema = StructType([
    StructField("Date", StringType(), True),
    StructField("Time", StringType(), True),
    StructField("Company", StringType(), True),
    StructField("Sector", StringType(), True),
    StructField("Industry", StringType(), True),
    StructField("Open", DoubleType(), True),
    StructField("High", DoubleType(), True),
    StructField("Low", DoubleType(), True),
    StructField("Close", DoubleType(), True),
    StructField("Adj_Close", DoubleType(), True),
    StructField("Volume", IntegerType(), True)
])

# Read streaming data from Kafka
df_kafka_raw = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
    .option("subscribe", kafka_topic) \
    .option("startingOffsets", "earliest") \
    .load()

# Decode the Kafka message (value) from binary to UTF-8 string
df_kafka_decoded = df_kafka_raw.select(col("value").cast("string").alias("message"))

# Parse the JSON array string into a DataFrame
df_kafka_parsed = df_kafka_decoded.select(from_json(col("message"), ArrayType(schema)).alias("data"))

# Flatten the nested array of rows into a single DataFrame
df_flattened = df_kafka_parsed.select(explode(col("data")).alias("data")).select("data.*")

# Debugging: Print schema and some rows
df_flattened.printSchema()

### Transformations ###

# 1. Datetime Handling: Convert Date from string to DateType and Time from string to TimestampType
df_flattened = df_flattened.withColumn("Date", to_date(col("Date"), "yyyy-MM-dd"))
df_flattened = df_flattened.withColumn("Time", to_timestamp(col("Time"), "HH:mm:ss").cast(TimestampType()))

# Combine Date and Time to create a Timestamp column
df_flattened = df_flattened.withColumn("Datetime", to_timestamp(concat_ws(" ", col("Date"), date_format(col("Time"), "HH:mm:ss")), "yyyy-MM-dd HH:mm:ss"))

# Drop the original Date and Time columns
df_flattened = df_flattened.drop("Date", "Time")

# 2. Price Range: Calculate price range(diff) (High - Low)
df_flattened = df_flattened.withColumn('Price_Range', col('High') - col('Low'))

# 3. Daily Return: Calculate daily return ((Close - Open) / Open * 100)
df_flattened = df_flattened.withColumn("Daily_Return", (col("Close") - col("Open")) / col("Open") * 100)

# 4. Price Category: Categorize based on closing price
df_flattened = df_flattened.withColumn("Price_Category", when(col("Close") < 100, "Low")
                                   .when(col("Close").between(100, 500), "Medium")
                                   .otherwise("High"))

# 5. Volatility Percentage Difference Between High and Low Prices
df_flattened = df_flattened.withColumn("Volatility_percentage", ((col("High") - col("Low")) / col("Close")) * 100)

# 6. Extract Additional Time-Based Features from 'Datetime'
df_flattened = df_flattened.withColumn("Year", year(col("Datetime"))) \
       .withColumn("Month", month(col("Datetime"))) \
       .withColumn("Day", dayofmonth(col("Datetime"))) \
       .withColumn("Hour", hour(col("Datetime"))) \
       .withColumn("Minute", minute(col("Datetime")))\
       .withColumn("Weekday", date_format(col("Datetime"), "E"))

df_flattened.printSchema()

### Write the transformed streaming data to BigQuery ###
query = df_flattened.writeStream \
    .format("bigquery") \
    .option("table", f"{project_id}.{dataset_id}.{table_id}") \
    .option("temporaryGcsBucket", gcs_bucket_name) \
    .option("checkpointLocation", checkpoint_location) \
    .outputMode("append") \
    .trigger(processingTime="2 minutes") \
    .start()


# Wait for the streaming to finish
query.awaitTermination()
