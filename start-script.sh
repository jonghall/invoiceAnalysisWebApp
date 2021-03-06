#!/bin/bash
# activate venv for Python
source /opt/venv/bin/activate
cd /app

# Start the second process
celery --app=invoiceAnalysis.celery worker  --concurrency=4 -l INFO --uid worker --gid worker&
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start Celery: $status"
  exit $status
fi

uwsgi --ini uwsgi.ini&
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start uwsgi server: $status"
  exit $status
fi


# Naive check runs checks once a minute to see if either of the processes exited.
# This illustrates part of the heavy lifting you need to do if you want to run
# more than one service in a container. The container exits with an error
# if it detects that either of the processes has exited.
# Otherwise it loops forever, waking up every 60 seconds

while sleep 60; do
  ps aux |grep celery |grep -q -v grep
  PROCESS_2_STATUS=$?
  ps aux |grep uwsgi |grep -q -v grep
  PROCESS_3_STATUS=$?

  # If the greps above find anything, they exit with 0 status
  # If they are not both 0, then something is wrong
  if [ $PROCESS_2_STATUS -ne 0 -o $PROCESS_3_STATUS -ne 0 ]; then
    echo "One of the processes has already exited."
    exit 1
  fi
done

