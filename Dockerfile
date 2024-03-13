FROM python:3.10.12

WORKDIR /usr/src/app

COPY requirements.txt .

# For fixing ImportError: libGL.so.1: cannot open shared object file: No such file or directory
RUN apt-get update
RUN apt install -y libgl1-mesa-glx

RUN pip install -r requirements.txt

COPY index.py .
COPY Arial.ttf .

ENTRYPOINT  ["python"]
CMD ["./index.py"]
