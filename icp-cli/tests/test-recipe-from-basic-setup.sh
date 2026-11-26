#!/usr/bin/env bash
# Test the Basilisk end-user flow from a clean Ubuntu 24.04.
#
# Usage:
#   docker build -t basilisk-basic -f icp-cli/tests/Dockerfile.basic-setup .
#   docker run --rm -v $PWD:/basilisk -w /basilisk basilisk-basic \
#       bash icp-cli/tests/test-recipe-from-basic-setup.sh
#
# 1. A wrong recipe sha256 stops the build: the template's pin is enforced.
# 2. This checkout's recipe deploys a canister that answers.
# 3. The template as published, with its pinned recipe, builds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_RECIPE="$REPO_ROOT/icp-cli/recipe/recipe.hbs"

python3 -m venv /tmp/venv
source /tmp/venv/bin/activate
pip install -e "$REPO_ROOT"

# The hello-world template as `icp new` makes it, in directory $1.
new_project() {
    cp -r "$REPO_ROOT/icp-cli/templates/hello-world" "$1"
    rm -rf "$1/.icp" "$1/.basilisk"
    sed -i 's/{{project-name}}/hello/g' "$1/icp.yaml"
}

new_project /tmp/wrong-pin
sed -i "s|^\( *\)sha256: .*|\1sha256: $(printf '0%.0s' {1..64})|" /tmp/wrong-pin/icp.yaml
if OUTPUT=$(cd /tmp/wrong-pin && icp build 2>&1); then
    echo "Error: icp built with a recipe whose sha256 does not match the pin"
    exit 1
fi
if ! grep -q "checksum mismatch" <<< "$OUTPUT"; then
    echo "Error: the build failed, but not on the recipe's sha256:"
    echo "$OUTPUT"
    exit 1
fi
echo "A wrong recipe sha256 stops the build"

new_project /tmp/test-project
sed -i "s|^\( *\)type: .*recipe.hbs$|\1type: file://$LOCAL_RECIPE|" /tmp/test-project/icp.yaml
sed -i "s|^\( *\)sha256: .*|\1sha256: $(sha256sum "$LOCAL_RECIPE" | cut -d' ' -f1)|" /tmp/test-project/icp.yaml
cd /tmp/test-project
icp network start -d
icp deploy
icp canister call hello greet '("World")'
icp network stop

new_project /tmp/pinned-project
cd /tmp/pinned-project
icp build

echo "PASSED"
