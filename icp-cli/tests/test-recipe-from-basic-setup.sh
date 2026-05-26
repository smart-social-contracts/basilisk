#!/usr/bin/env bash
# Test the Basilisk end-user flow from a clean Ubuntu 24.04.
#
# Usage:
#   docker build -t basilisk-basic -f icp-cli/tests/Dockerfile.basic-setup .
#   docker run --rm -v $PWD:/basilisk -w /basilisk basilisk-basic \
#       bash icp-cli/tests/test-recipe-from-basic-setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 -m venv /tmp/venv
source /tmp/venv/bin/activate
pip install -e "$REPO_ROOT"

cp -r "$REPO_ROOT/icp-cli/templates/hello-world" /tmp/test-project
rm -rf /tmp/test-project/.icp /tmp/test-project/.basilisk
sed -i 's/{{project-name}}/hello/g' /tmp/test-project/icp.yaml
cd /tmp/test-project

icp network start -d
icp deploy

icp canister call hello greet '("World")'
if [ "$?" -ne 0 ]; then
    echo "Error: failed to call canister"
    exit 1
fi

echo "PASSED"
