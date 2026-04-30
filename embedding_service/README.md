# Embedding service
This service is intended to run on the **semant** server (due to memory requirements).

## Installation and Setup
- Clone repository: 
```bash 
git clone https://github.com/DCGM/semant-demo.git 
```
- Go to **embedding_service** folder: 
```bash
cd embedding_service
```
- Create a virtual environment: 
```bash
python3 -m venv .venv 
```
- Activate the virtual environment:
```bash
source .venv/bin/activate
```
- Install requirements: 
```bash
pip install -r requirements.txt
```

> **Note — GPU support for PyTorch:** `pip install torch` defaults to the CPU-only build from PyPI. If the service ends up running on CPU only, install PyTorch explicitly from the CUDA index **after** installing the requirements:
> ```bash
> pip install torch --extra-index-url https://download.pytorch.org/whl/cu130
> ```
> Replace `cu130` with the CUDA version on your machine (e.g. `cu128`, `cu124`). See [pytorch.org/get-started](https://pytorch.org/get-started/locally/) to find the right URL.

## Running the service
### Without screen
- Activate the virtual environment: 
```bash
source .venv/bin/activate 
```
- Run: 
```bash
python3 run.py
``` 
### With screen
- You can use ```screen``` to keep the service running after disconnecting from the server.
- Create a screen: 
```bash
screen -S <name>
```
- Activate the virtual environment: 
```bash
source .venv/bin/activate 
```
- Run: 
```bash
python3 run.py
``` 
- Leave screen: ```Ctrl+A``` then ```d```
- Go back to the screen: 
```bash 
screen -r <name>
```
- Exit a screen:
 ```bash
 exit
 ```
- View screens: 
```bash
screen -ls
```

## Connect to the service
- Use a ssh tunnel.
- Example: ```ssh -L 8001:localhost:8001 xlogin00@semant.fit.vutbr.cz```