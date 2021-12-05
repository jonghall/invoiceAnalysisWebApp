# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM tiangolo/uwsgi-nginx-flask:python3.9
#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"
#
# Install NGINX to test.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
ENV PATH="/app/.local/bin:${PATH}"
WORKDIR /app

RUN  apt-get update && COPY . /app && pip install -r requirements.txt
CMD ./start-script.sh