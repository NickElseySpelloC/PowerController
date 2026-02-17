# Build and Install Python 3.13 on a RaspberryPi

PowerController requires Python v3.13 or later. As at the time of writing, compiled binaries aren't yet available for the Pi, so you will need to compile them from the source code. We recommend a Pi with a good amount of free memory and swap space. 

## Check available RAM and swap

```bash
free -h
```

If available RAM is low (<100 MB), consider increasing swap:
```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile

# Set CONF_SWAPSIZE=2048 (or higher)
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

Now build python 3.13 from source. This will install Python as **/usr/local/bin/python3.13**.
```bash
sudo apt update

sudo apt install -y make build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
  libffi-dev liblzma-dev

cd /usr/src
sudo wget https://www.python.org/ftp/python/3.13.0/Python-3.13.0.tgz
sudo tar xzf Python-3.13.0.tgz

cd Python-3.13.0
sudo ./configure --enable-optimizations
sudo make -j $(nproc)
sudo make altinstall
```

⚠️ Use make altinstall so you don’t overwrite the system Python.