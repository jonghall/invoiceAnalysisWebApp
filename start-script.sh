#!/bin/bash

# Start the first process
redis-server &
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start Redis: $status"
  exit $status
fi

# Start the second process
celery --app=invoiceAnalysis.celery worker -l INFO &
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start Celery: $status"
  exit $status
fi

uwsgi --ini uwsgi.ini &
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start uwsgi server: $status"
  exit $status
fi


