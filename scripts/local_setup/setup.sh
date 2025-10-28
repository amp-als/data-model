#!/bin/bash

ENV_NAME="amp-als"
micromamba env create -f environment.yml -n ${ENV_NAME}
micromamba activate ${ENV_NAME}
micromamba install python=3.10 
micromamba install pip nodejs
pip install schematicpy linkml==v1.8.1 jsonata-python 
npm install -g json-dereference-cli

wget -O $CONDA_PREFIX/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && chmod a+x $CONDA_PREFIX/bin/yq

bash <(curl -fsSL https://raw.githubusercontent.com/babashka/babashka/master/install) --dir "$CONDA_PREFIX/bin"
[ ! -d "retold" ] && git clone --depth 1 https://github.com/anngvu/retold.git


