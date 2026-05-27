# Recipe Tests

## CI (automated)

The `test-recipe.yml` workflow builds the `basilisk-basic` Docker image and runs
`test-recipe-from-basic-setup.sh` inside it. It triggers on PRs that touch
`icp-cli/**` and can also be dispatched manually.

## Manual testing

Build the test image (once, from the repo root):

```bash
docker build -t basilisk-basic -f icp-cli/tests/Dockerfile.basic-setup .
```

Start a container with the local repo mounted:

```bash
docker run -it --rm \
  -v "$PWD":/basilisk-src:ro \
  basilisk-basic bash
```

Inside the container, run the end-user flow with your local Basilisk source:

```bash
cd /tmp
icp new my_project \
  --git https://github.com/smart-social-contracts/basilisk \
  --subfolder icp-cli/templates/hello-world
cd my_project

# Install local Basilisk instead of the PyPI release
cp -r /basilisk-src /tmp/basilisk
pip install /tmp/basilisk

icp network start -d
icp deploy

icp canister call my_project greet '("World")'
```