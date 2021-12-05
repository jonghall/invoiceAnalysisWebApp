# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM tiangolo/uwsgi-nginx-flask:python3.9
#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"
#
# Install NGINX to test.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
ENV PATH="/app/.local/bin:${PATH}"

RUN apt-get update
RUN python3 -m venv /opt/venv
RUN source /opt/venv/bin/activate
RUN adduser worker
RUN usermod -aG sudo worker
RUN echo "worker ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers
RUN chown worker:worker /app
COPY --chown=worker:worker . /app
WORKDIR /app

RUN pip install -r requirements.txt

CMD ./start-script.sh