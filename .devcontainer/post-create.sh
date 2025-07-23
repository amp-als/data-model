#!/bin/bash

# Default image uses Python 3.12, which is incompatible

curl -fsSL https://pyenv.run | bash
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
pyenv install 3.10.18
pyenv global 3.10.18
pip install schematicpy==25.7.1 linkml==v1.8.1 jsonata-python
npm install -g json-dereference-cli
sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && sudo chmod a+x /usr/local/bin/yq
sudo bash < <(curl -s https://raw.githubusercontent.com/babashka/babashka/master/install)
[ ! -d "retold" ] && git clone --depth 1 https://github.com/anngvu/retold.git
