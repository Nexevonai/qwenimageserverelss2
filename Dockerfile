# --- 1. 基础镜像和环境设置 ---
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ="Etc/UTC"
ENV COMFYUI_PATH=/root/comfy/ComfyUI
ENV VENV_PATH=/venv

# --- 2. 安装系统依赖 ---
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ffmpeg \
    wget \
    unzip \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# --- 3. 设置 Python 虚拟环境 (VENV) ---
RUN python -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"
RUN /venv/bin/python -m pip install --upgrade pip

# --- 4. 安装 ComfyUI 和核心 Python 包 ---
RUN /venv/bin/python -m pip install comfy-cli
RUN comfy --skip-prompt install --nvidia --cuda-version 12.4

# --- 关键修改：明确安装所有handler需要的依赖 ---
RUN /venv/bin/python -m pip install \
    opencv-python \
    imageio-ffmpeg \
    runpod \
    requests \
    websocket-client \
    boto3 \
    huggingface-hub

# --- 5. 创建 VibeVoice 模型目录 ---
RUN mkdir -p \
    $COMFYUI_PATH/models/vibevoice/tokenizer \
    $COMFYUI_PATH/models/vibevoice/VibeVoice-Large

# --- 6. 下载 VibeVoice 模型文件 ---
# Download VibeVoice-Large model (~18.7GB)
RUN /venv/bin/huggingface-cli download aoi-ot/VibeVoice-Large \
    --local-dir $COMFYUI_PATH/models/vibevoice/VibeVoice-Large \
    --local-dir-use-symlinks False

# Download Qwen2.5-1.5B tokenizer files
RUN /venv/bin/huggingface-cli download Qwen/Qwen2.5-1.5B \
    tokenizer_config.json vocab.json merges.txt tokenizer.json \
    --local-dir $COMFYUI_PATH/models/vibevoice/tokenizer \
    --local-dir-use-symlinks False

# --- 7. 安装 VibeVoice 自定义节点 ---
RUN git clone https://github.com/Enemyx-net/VibeVoice-ComfyUI.git $COMFYUI_PATH/custom_nodes/VibeVoice-ComfyUI

# --- 8. 安装 VibeVoice Python 依赖 ---
RUN /venv/bin/python -m pip install \
    diffusers \
    accelerate \
    transformers>=4.51.3 \
    sentencepiece \
    soundfile

# --- 8. 复制脚本并设置权限 ---
# --- 关键修改：不再复制 workflow_api.json ---
COPY src/start.sh /root/start.sh
COPY src/rp_handler.py /root/rp_handler.py
COPY src/ComfyUI_API_Wrapper.py /root/ComfyUI_API_Wrapper.py

RUN chmod +x /root/start.sh

# --- 9. 定义容器启动命令 ---
CMD ["/root/start.sh"]
