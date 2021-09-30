# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM tiangolo/uwsgi-nginx-flask:python3.9

#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"
#
# Install NGINX to test.
COPY . /app
WORKDIR /app
RUN apt-get update -y
RUN apt-get install redis-server redis-tools -y


COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
CMD ./start-script.sh
