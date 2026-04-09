FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y git wget && rm -rf /var/lib/apt/lists/*

# see-through 레포 클론
RUN git clone https://github.com/shitagaki-lab/see-through.git
WORKDIR /app/see-through

# 심링크
RUN ln -sf common/assets assets

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# RunPod SDK
RUN pip install --no-cache-dir runpod

# 모델 weights를 빌드 시점에 다운로드 (cold start 단축)
RUN huggingface-cli download layerdifforg/seethroughv0.0.2_layerdiff3d
RUN huggingface-cli download 24yearsold/seethroughv0.0.1_marigold

# handler 복사
COPY handler.py /app/handler.py

WORKDIR /app
CMD ["python", "-u", "handler.py"]
