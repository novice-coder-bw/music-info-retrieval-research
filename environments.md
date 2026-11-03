---
title: Modify environment
description: >-
  In this guide, we'll learn about environments and how Studios handle them. In
  short, each Studio corresponds to a single environment. This provides nice...
canonical: 'https://lightning.ai/docs/platform/build/ai-studio/modify-environment'
---
# Modify environment {#modify-environment}

In this guide, we'll learn about environments and how Studios handle them. In short, each Studio corresponds to a single environment. This provides nice work isolation and removes a lot of the need to manage environments yourself.

## What is an environment? {#what-is-an-environment}

On a laptop it is necessary to isolate each Python project from each other to avoid dependency conflicts. For example, project A may require pandas=1.0.0 and project B may require pandas=1.1.0. Both pandas cannot live on the same laptop, so you create 2 environments, each with a different pandas.

An environment is a kind of container that bundles all the necessary dependencies for a particular Python project.

In an ideal world, you would have a new laptop for each different project, but that is of course too expensive and impractical.  In Lightning, that's how we've approached it. Think of each Studio as its own laptop with its own completely isolated environment. Studios can only have a single environment.

Tip: Watch our lecture on environments if you haven't learned these before.

[Our lecture on environments](https://www.youtube.com/watch?v=WHWsABk4Ejk&amp;t=2s)

## Manage environments {#manage-environments}

### conda {#conda}

Lightning Studios include a default conda environment that is automatically sourced into all shells, batch jobs, etc. For most use-cases, the conda environment should be the only environment in the Studio. To import an existing conda environment, use `conda env update --file "env.yml"`.

### uv {#uv}

For a more advanced set-up, Lightning Studios come with `uv` pre-installed. You can either install in the Studio environment directly with `uv pip` or, if you have a `pyproject.toml` file, get started with `uv sync`.

### venv {#venv}

Typical virtual environments should be avoided in Lightning Studios as they can cause poor performance, however, you can safely create a virtual environment with `uv venv`.

## Environment principles {#environment-principles}

These are the key principles around environments with Lightning Studios.

### One Studio, one environment {#one-studio-one-environment}

We've designed Studios to be isolated environments. Each Studio is a single environment. Install whatever packages, files, and dependencies you want. When you need to create a new environment, simply create a new Studio.

![Each Studio has its own isolated environment](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/b0160399-8aca-4038-9f70-c68dcd23c289.png)

### One Studio, one task {#one-studio-one-task}

We recommend that you set up one Studio per task. A task can mean an endpoint, a finetuning workflow, a training workflow, etc. Think about it as a microservice or a self-contained task.

For example, if I'm working on a model and have different parts of that model (training, finetuning, data prep, etc...), I'll set up a Studio for each of those because each step of the model pipeline requires different dependencies. The code under the hood likely still comes from a single repository hosted on Github.

![Create a Studio for each step of the model pipeline](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/7442f8ef-06a3-4b22-a2c1-dcaa74395f3e.png)

### Install dependencies {#install-dependencies}

There's nothing special you need to know to install dependencies. Just do what you would do on your laptop. In a Studio, open a Studio terminal, and install whatever dependencies you need.

Use **pip**, **conda**, **poetry**, **apt-get**, or build libraries from source.

![Install anything you want in your environment](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/7d5a4063-e12b-4e18-95ea-c95330c827ce.png)

Studios give you full control to change cuda, python versions, and more. Open the environments panel to manage more environment details.

![The environment panel is below the CPU / GPU selector in the Studio environment popover](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/877966cf-a44e-437d-9d66-d3b1a9fd1b10.png)

### Python Versions {#python-versions}

The studio ships with Python 3.10.10 as the default version. You can select a different version of python for the studio in the environments panel, by clicking on the python version number.

![The environment panel is below the CPU / GPU selector in the Studio environment popover](https://storage.googleapis.com/lightning-avatars/litpages/01jrbttkedg3tevwqb6sdnejx8/c610d30c-007d-4fd1-8b35-9972c66bfaea.png)

This will open the python version modal, which will allow you to select the python version to use in this studio.

![Selecting the version of python to use in this studio](https://storage.googleapis.com/lightning-avatars/litpages/01jrbttkedg3tevwqb6sdnejx8/88ba9e8f-fcf4-4cf9-8460-e7e667123ad5.png)

It is important to note that when you change the python version, you will have to reinstall all dependencies installed via python package managers.

### Drivers and CUDA versions {#drivers-and-cuda-versions}

The Studio ships with a fixed NVIDIA driver. Studios also ship with CUDA pre-installed. We test quite thoroughly and pre-install the most stable version but you can install a new version using conda.

```bash
conda install cudatoolkit=[X.X]
```

### Environments are persistent {#environments-are-persistent}

Persistence means that anything you install in an environment will always be there. For example, start a Studio, verify it's missing a dependency (try cowsay).

![Cowsay isn't installed](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/10d16a5d-9ee0-4fc6-94c6-0c0489a90b7f.png)

Now, install cowsay.

![Cowsay is now installed](https://storage.googleapis.com/lightning-avatars/litpages/01hkvnrfreb3njkwb1p4chd7eh/602f0b6c-873a-453f-bcdf-3d9c266af291.png)

Restart the Studio or change GPUs and you'll notice you don't need to reinstall cowsay.

This guide goes into details on [environment persistence](https://lightning.ai/docs/platform/build/ai-studio/environment-persistence.md).

## Automate with SDK {#automate-with-sdk}

Everything we've discussed here can be done programmatically with the lightning SDK.

```python
# Install the Lightning SDK
# pip install lightning-sdk

# login to the platform
# export LIGHTNING_USER_ID=0000-0000-0000-0000-0000-0000-0000-0
# export LIGHTNING_API_KEY=0000-0000-0000-0000-0000-0000-0000-0

from lightning_sdk import Studio

# Start the studio
s = Studio(name="model-1-server", teamspace="model-a", user="will")
print("starting Studio...")
s.start()

# prints Status.Running
print(s.status)

print(s.run("pip install cowsay"))

print("Stopping Studio")
s.stop()

```

## FAQ {#faq}

### Can I turn off Conda? {#can-i-turn-off-conda}

Yes, using [Base Studios](https://lightning.ai/docs/platform/build/ai-studio/base-studios.md)! You can define a template for launching Studios using a Base Studio, including selecting the `Coding Environment` to have a `Fresh environment` that will have a clean environment with no pre-installed tools or libraries.

---

---
title: Environment persistence
description: >-
  Studios persist their environments when sleeping and switching machines. Jobs
  use forks of the environment so that the environment you develop is the
  same...
canonical: 'https://lightning.ai/docs/platform/build/ai-studio/environment-persistence'
---
# Environment persistence {#environment-persistence}

Studios persist their environments when sleeping and switching machines. Jobs use forks of the environment so that the environment you develop is the same you scale.

[Studio environments persist when switching machines or sleeping](https://assets.lightning.ai/Docs_Studios_MP4/Docs_Studios_ChangeGPUs_PersistentDependencies.mp4)

There are a lot of nuances and details about how we do persistency that we will not cover in this guide. However, we will discuss the common questions that cover the main use cases.

## Filesystem {#filesystem}

Everything in the Studio home (`~`, `/teamspace/studios/this_studio`) is persisted except for `node_modules`, which should be recreated when needed. Download any files, build packages and whatever else you want!

## Python environment {#python-environment}

Any packages you install or build are persisted. You can install packages in editable mode, edit your site-packages, and anything else you might need.

[Install your packages; they'll persist](https://assets.lightning.ai/Docs_Studios_MP4/Docs_Studios_EnvironmentPersistency_InstallPackages.mp4)

Note that we don't allow creating additional environments or virtual environments within the Studio. If you need to create a new environment, start a new Studio.

[Need a new environment? Start a new studio!](https://assets.lightning.ai/Docs_Studios_MP4/Docs_Studios_EnvironmentPersistency_InstallPackages2-NewStudio.mp4)

## VSCode settings {#vscode-settings}

Any extensions installed, or changes you make to your VSCode on the Studio will apply to the VSCode across ALL your Studios. For example, if you install [Github Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot), it will be available in all your Studios.

## JupyterLab settings {#jupyterlab-settings}

JupyterLab settings are not persisted.

## System packages {#system-packages}

Any system packages you install will be persisted. We recommend you install everything via **apt-get**.

[Use apt-get to install, update, and remove software packages](https://assets.lightning.ai/Docs_Studios_MP4/Docs_Studios_EnvironmentPersistency_InstallSystemPackages.mp4)

If you install packages in non standard ways or place them in non standard locations, there is a chance they will not be persisted. This is for your security.

If you rely additional binaries that aren't available through **apt-get**, we recommend placing them somewhere in your Studio home (`~`, `/teamspace/studios/this_studio`) and adding them to the `PATH` in your `.zshrc`, `.bashrc`, `.profile`, or similar. For example:

```bash
export PATH="/teamspace/studios/this_studio/bin:${PATH}"
```

## Docker images {#docker-images}

Feel free to build docker images on the Studio. They are currently not persisted, if you are interested in this feature please reach out to us at support@lightning.ai.
