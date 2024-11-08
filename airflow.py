from datetime import datetime, timedelta 
from airflow import DAG from airflow.operators.bash import BashOperator  

# Define default arguments 
default_args = {     'owner': 'airflow',     'retries': 1,     'retry_delay': timedelta(minutes=1), }  
# Define the DAG with DAG(     'spark_test_job',     default_args=default_args,     description='Run spark-test.py every 5 minutes',     schedule_interval='*/5 * * * *',  # This cron expression means every 5 minutes     start_date=datetime(2023, 1, 1),     catchup=False,  # Do not backfill ) as dag:      
# Task to run the spark-test.py script     
run_spark_test = BashOperator(         task_id='run_spark_test',         bash_command='python /path/to/spark-test.py',
  # Replace with the full path to spark-test.py     )
