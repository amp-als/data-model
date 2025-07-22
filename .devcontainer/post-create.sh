#!/bin/bash

pip3 install schematicpy==24.7.2 linkml==v1.8.1 jsonata-python
npm install -g json-dereference-cli
sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && sudo chmod a+x /usr/local/bin/yq
sudo bash < <(curl -s https://raw.githubusercontent.com/babashka/babashka/master/install)
[ ! -d "retold" ] && git clone --depth 1 https://github.com/anngvu/retold.git
