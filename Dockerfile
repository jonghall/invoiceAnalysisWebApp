# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM tiangolo/uwsgi-nginx-flask:python3.9
#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"
#
# Install NGINX to test.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
RUN apt-get update
RUN python3 -m venv /opt/venv
RUN source /opt/venv/bin/activate
COPY . /app
WORKDIR /app
RUN apt-get install redis-server redis-tools -y
RUN pip install -r requirements.txt
CMD ./start-script.sh