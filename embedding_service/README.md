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