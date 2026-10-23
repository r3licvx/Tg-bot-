FROM python:3.10-slim-bookworm

RUN apt update && apt upgrade -y && \
    apt install -y git && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /FileToLink

WORKDIR /FileToLink

COPY . /FileToLink

# Port expose (আপনার bot PORT variable ব্যবহার করে)
EXPOSE 8080

# Environment variable হিসেবে PORT সেট করুন
ENV PORT=8080

CMD ["python", "main.py"]
