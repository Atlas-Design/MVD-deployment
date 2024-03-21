# Installation
Clone the repo and run
```bash
  cd cli 
  pip install .
```
Or if using git with ssh
```bash
    pip install git+ssh://git@github.com/Atlas-Design/MVD-deployment.git#subdirectory=cli
```
Or
```bash
    pip install git+https://github.com/Atlas-Design/MVD-deployment.git#subdirectory=cli
```

After that run for more info:
```bash
    sd_cli --help
```

# Development
In order to develop the CLI, you need to install the package in development mode. This can be done by running the following command (preferably in some kind of venv):
```bash
    pip install --editable .
```

After that you can run the CLI with:
```bash
    sd_cli --help
```
