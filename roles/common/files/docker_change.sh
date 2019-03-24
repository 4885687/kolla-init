#!/bin/bash
set -x -v
python -c "import docker;print(docker.Client())"
if [ $? -ne 0 ]
then 
  pip uninstall docker -y; pip uninstall docker-py  -y
  pip install docker==3.3.0 && pip install docker-py==1.10.6
  python -c "import docker;print(docker.Client())"
fi
