# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM python:3.9-slim-buster

#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"

#
# Install NGINX to test.
COPY . /app
WORKDIR /app
RUN apt-get update -y && \
    apt-get install -y python-pip python-dev

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
ENTRYPOINT [ "python" ]
ENV FLASK_APP=invoiceAnalysis
CMD [ "app.py" ]