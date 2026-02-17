# Installing the Prerequisites

The prerequisites for the PowerController application are:

1. [Python v3.13](https://www.python.org/downloads/release/python-3130/)
2. [UV package manager](https://docs.astral.sh/uv/getting-started/)

We'll step you through each of these in turn:

# STEP 1: Checking and installing Python v3.13

Check to see which version of Python is installed:
```bash
python3 --version
```

If Python 3.13 is installed, you should see something like:
```bash
Python 3.13.x
```
If the command is not found, or the version is lower than 3.13, install python3 using one of the sections below

## Installing Python v3.13 on Linux

We'll use apt to install Python 3.13 on Linux

```bash
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev
```

## Installing Python v3.13 on macOS

We'll use Homebrew to install Python 3.13 on a Mac

**Check if Homebrew is installed**

```bash
brew --version
```

If Homebrew is not installed, install it with:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
After installation, restart your terminal.

**Install Python 3.13**
```bash
brew update
brew install python@3.13
```

**Ensure Python 3.13 is being used**

```bash
brew link python@3.13 --force
```

Verify that v3.13 is not the default:
```bash
python3 --version
```

## Installing Python v3.13 on a RaspberryPi

As at the time of writing, Python 3.13 compiled binaries aren't yet available for the Pi, so you will need to compile them from the source code using [this guide](raspberry_pi_python.md).

---

# STEP 2: Install git

git is needed to download the PowerController app from GitHub. Check if git is installed
```bash
git --version
```

If it's not installed, follow the steps below.

## Installing git on Linux and RaspberryPi
```bash
sudo apt update
sudo apt install git
```

## Installing git on macOS

```bash
brew install git
```

# STEP 3: Install the UV package manager 

uv is extremely fast and replaces tools like pip, venv, and pip-tools.


## Installing UV on Linux and RaspberryPi

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal session, then verify:
```bash
uv --version
```


## Installing UV on macOS
```bash
brew install uv

# Verify installation:
uv --version
```

## Ensuring uv is on Your PATH

If uv installs but the command is not found, add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload:
```bash
# Reload ZShell
source ~/.zshrc

# Reload bash
source ~/.bashrc
```

---

# Next Step >> [Setup your Shelly devices](shelly_setup.md)
