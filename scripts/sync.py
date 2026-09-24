#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GithubStar 数据同步 + 自动归类

输入（data/ 目录）：
  stars_raw.json          - `gh api --paginate user/starred` 的 NDJSON 原始输出（每次同步覆盖）
  recommendations.jsonl   - 每日热点推荐项目，一行一条（由 cron 每日追加）
输出：
  repos.json              - 单一事实源：{full_name, url, description, language, stars,
                            topics, category, source, added_at, note}

用法：
  python3 scripts/sync.py            # 同步/合并 + 归类，写 data/repos.json
  python3 scripts/sync.py --report   # 额外打印分类统计与未归类清单
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPOS = DATA / "repos.json"

# ── 分类定义（顺序即优先级） ────────────────────────────────────────────
CATEGORIES = [
    "飞控与无人机",
    "电磁仿真与超表面",
    "嵌入式与单片机",
    "硬件设计与 EDA",
    "无线通信与感知",
    "AI Agent 与 LLM 工具链",
    "知识管理与笔记",
    "AI 模型与视觉",
    "开发工具与系统资源",
]

# 关键词规则：命中任一即归入该类（按 CATEGORIES 顺序判定）
RULES: dict[str, list[str]] = {
    "飞控与无人机": [
        "ardupilot", "px4", "crazyflie", "drone", "quadrotor", "multicopter", "uav",
        "flight controller", "飞控", "无人机", "ego-planner", "dronebridge", "langostino",
        "swiftwing", "图传遥控", "bittensor", "lime", "nano quadcopter", "mission planner",
    ],
    "嵌入式与单片机": [
        "embedded", "mcu", "microcontroller", "micro-python", "micropython", "rtos",
        "zephyr", "freeRTOS", "esp32", "esp8266", "stm32", "cortex-m", "risc-v", "ch32v",
        "bouffalo", "bl702", "rt-thread", "arduino", "firmware", "tinyml", "lvgl", "littlevgl",
        "toit", "renode", "eide", "openmv", "camera module", "单片机", "嵌入式", "m0sense",
        "probe-rs", "openocd", "hardware-in-the-loop", "real board", "liet", "i2c", "spi",
    ],
    "硬件设计与 EDA": [
        "kicad", "altium", "pcb", "eda", "easyeda", "嘉立创", "schematic", "bom",
        "opencascade", "occt", "cad", "dwg", "dxf", "shapr3d", "atopile", "ardep",
        "kistack", "circuit", "电路", "原理图", "3d printing",
    ],
    "无线通信与感知": [
        "wifi", "wi-fi", "csi", "lora", "nrf24", "zigbee", "bluetooth", "gnss", "gps",
        "rtklib", "imu", "slimevr", "nanomsg", "vofa", "serial debug", "telemetry",
        "datalink", "sdr", "rf ", "radar", "感知",
    ],
    "电磁仿真与超表面": [
        "cst studio", "cst", "fdtd", "metamaterial", "metasurface", "hfss", "antenna",
        "electromagnetic", "微波", "仿真", "absorber", "rcs", "polarization", "photonics",
        "超表面", "吸波", "电磁",
    ],
    "知识管理与笔记": [
        "obsidian", "notebooklm", "note-taking", "knowledge graph", "knowledge base", "wiki",
        "second brain", "pkm", "tutor", "笔记", "知识", "book", "tutorial", "handbook",
        "learning-notes", "guide", "教程", "教材", "awesome-",
    ],
    "AI Agent 与 LLM 工具链": [
        "agent", "llm", "mcp", "model context protocol", "claude", "codex", "openai",
        "copilot", "harness", "prompt", "skill", "openclaw", "opencode", "cline", "qwen-code",
        "spec-driven", "deep research", "computer use", "browser for ai", "scraping",
    ],
    "AI 模型与视觉": [
        "segment anything", "segment-anything", "yolo", "diffusion", "speech", "asr", "tts",
        "vocoder", "fine-tune", "finetune", "inference", "onnx", "gguf", "transformer",
        "reinforcement learning", "monocular", "view synthesis", "image", "vision", "nlp",
        "model compression", "quantization", "语音", "识别", "视觉",
    ],
}

# 人工校正：full_name -> 分类（优先级最高，用于规则误判的个案）
OVERRIDES: dict[str, str] = {
    # ---- 2026-09-25：逐条显式归类（免规则串味；仪器/融合/RTK 三类易误判） ----
    "AndersOnLin4/cst-mcp": "电磁仿真与超表面",                  # CST Studio 的 MCP 服务器（吸波体单元胞自动化）
    "hongwei1-c/RF-AIagent": "电磁仿真与超表面",                  # HFSS 自动化 agent（射频设计）
    "OpenLithoHub/DiffNano": "电磁仿真与超表面",                  # 可微纳米光子学/超表面逆设计
    "Nishandhini0311/Patch-Antenna-with-Metamaterial-Superstrate": "电磁仿真与超表面",  # openEMS 超材料覆层算例
    "knarfS/smuview": "硬件设计与 EDA",                          # 仪器上位机（sigrok 前端）
    "abduznik/instrumation": "硬件设计与 EDA",                    # RF 测试台 HAL（仪器类）
    "DavidClawson/OpenScope-2C53T": "硬件设计与 EDA",             # 示波器逆向与固件开发（仪器类）
    "wagiminator/CH32X035-USB-PD-Tester": "硬件设计与 EDA",       # USB PD 协议测试设备
    "vicharak-in/shrike": "硬件设计与 EDA",                       # MCU+FPGA 开发板（HDL 先例归 EDA）
    "0xShug0/audio.cpp": "AI 模型与视觉",                         # 音频推理引擎（同 llamafile/ds4 先例）
    "QwenAudio/SenseVoice": "AI 模型与视觉",                      # 端侧 ASR/情感识别模型
    "bupt-ai-cz/LLVIP": "AI 模型与视觉",                          # 可见光-红外配对数据集
    "Zhaozixiang1228/MMIF-CDDFuse": "AI 模型与视觉",              # 红外-可见光融合（CVPR23）
    "JinyuanLiu-CV/TarDAL": "AI 模型与视觉",                      # 红外-可见光融合+检测（CVPR22）
    "hli1221/imagefusion_densefuse": "AI 模型与视觉",             # DenseFuse 图像融合
    "Stefal/rtkbase": "无线通信与感知",                           # 自建 GNSS 基准站
    "GREAT-WHU/GREAT-PVT": "无线通信与感知",                      # 精密定位/导航软件
    "rsasaki0109/gnssplusplus-library": "无线通信与感知",          # C++20 GNSS 工具箱
    "Circuit-Digest/MLX90640-Thermal-Camera": "嵌入式与单片机",    # MLX90640 热像仪（同 PiThermalCam 先例）
    "PeterkoCZ91/esphome-wifi-csi": "嵌入式与单片机",             # ESPHome CSI 组件
    "x1958075990h-pixel/RuView_Radar_Lite": "嵌入式与单片机",      # ESP32 CSI 感知 DSP
    "esp-cpp/espp": "嵌入式与单片机",                             # ESP32 C++ 组件库
    "TheMaxMur/RS-Key": "嵌入式与单片机",                         # RP2350 硬件 passkey 固件
    "STMicroelectronics/stm32ai-modelzoo": "嵌入式与单片机",       # STM32 AI 模型库
    "gavinlyonsrepo/LCR_meter": "嵌入式与单片机",                  # Arduino 自制 LCR 表
    "Den41k92/crsf-link-tester": "飞控与无人机",                   # CRSF/ELRS 链路测试仪
    "HGSAFD8162/Expresslrs-Ghost-RX": "飞控与无人机",              # ELRS 被动遥测嗅探接收机
    "agamrossen/VolAnti": "飞控与无人机",                          # 声学无人机侦测
    "Ha22yX/Mother-Ship-Docking-Drone-System": "飞控与无人机",      # 双机对接相对定位
    "alireza787b/px4xplane": "飞控与无人机",                      # PX4 ↔ X-Plane 仿真桥

    # ---- 2026-09-23：规则未命中或误判（description 信息量不足 / 关键词串味） ----
    "zed-industries/zed": "开发工具与系统资源",            # 代码编辑器（star 列表新增）
    "mozilla-ai/llamafile": "AI 模型与视觉",              # 单文件分发的大模型推理（LLM in one file）
    "antirez/ds4": "AI 模型与视觉",                       # DeepSeek 4 Flash/PRO 本地推理引擎（C，Metal/CUDA/ROCm）
    "baidu-baige/sglang-kunlun": "AI 模型与视觉",          # SGLang 的昆仑 XPU 硬件插件
    "mmm1712/edge-ai-object-tracking-camera": "AI 模型与视觉",  # 本地边缘 AI 云台跟踪相机
    "sekigon-gonnoc/Pico-PIO-USB": "嵌入式与单片机",        # RP2040/RP2350 PIO 实现 USB 主机/设备
    "wiredopposite/OGX-Mini": "嵌入式与单片机",            # RP2040 USB 手柄模拟固件
    "Jana-Marie/Otter-Iron-PRO": "嵌入式与单片机",         # USB-PD 焊接台（与 AxxSolder 同类）
    "Mazin-O3/cpm-neo": "嵌入式与单片机",                  # C 实现的 CP/M 风格 OS
    "puddingstudio/MiSTerFin": "嵌入式与单片机",           # MiSTer FPGA 平台上的 Jellyfin 客户端
    "Mr-Mika/M-Gauge": "嵌入式与单片机",                   # CAN 总线数字仪表盘
    "SAM0-0/ATHER-OBD-READER": "嵌入式与单片机",           # 电动两轮 BMS CAN 读取器
    "CSS-Electronics/can-bus-reverse-engineering-skills": "嵌入式与单片机",  # CAN 逆向技能集（按领域归类，同 pcb-skill 先例）
    "kathoc/brickboy-dmg-fpgacore": "硬件设计与 EDA",      # Analogue Pocket openFPGA 核心（Verilog）
    "elerac/polanalyser": "电磁仿真与超表面",              # 偏振图像分析（Stokes/Mueller）
    "ecrc/bemfmm": "电磁仿真与超表面",                     # FMM 加速边界积分波散射求解器
    "eleweiz/Solving-full-wave-nonlinear-inverse-scattering-problems-with-back-propagation-scheme": "电磁仿真与超表面",  # 全波非线性逆散射
    "Rouf0x/splatfpv": "飞控与无人机",                     # 浏览器内 FPV 穿越机模拟器
    "ReconGrunt/FlipDeFlock": "无线通信与感知",            # Flipper Zero + ESP32 监控设备探测
    "Pouya-Mansournia/ros2-zero-to-robot": "飞控与无人机",  # ROS 2 机器人实战（误命中 book → 知识管理）
    "Pouya-Mansournia/warehouse-amr-ros2": "飞控与无人机",  # 多机器人 AMR 集群仿真（误命中 simulation → 电磁）
    "JackJu-HIT/SCAN-Planner-Pure-ROS2": "飞控与无人机",    # 轨迹优化器（ROS 2 精简版）
    "xiaoqi371317/SCAN-Planner-Ros2": "飞控与无人机",       # 轨迹优化器（Humble 适配版）
    "gepa-ai/gepa": "AI Agent 与 LLM 工具链",          # 提示词/代码反射式优化框架
    "twelvesec/PwnPad": "硬件设计与 EDA",                # 硬件攻防实验平台（自制 PCB）
    "optiland/optiland": "电磁仿真与超表面",              # 光学设计/可微光线追迹仿真库
    "tbs-trappy/source_one": "飞控与无人机",              # 开源 FPV 机架（结构件）
    "SweiryDev/MicroCNN-TangNano20k": "硬件设计与 EDA",   # Tang Nano 20K 上的 FPGA CNN 加速器
    "CardputerZero/Template": "嵌入式与单片机",           # Cardputer 模板工程（ESP32-S3）
    "sorinbotirla/Raspberry-Pi-FLIR-Lepton-Thermal-Imaging-Camera": "嵌入式与单片机",  # 树莓派 + FLIR Lepton 自制热像仪
    "skywalker1905/thermal-camera-viewer": "AI 模型与视觉",      # 热像仪桌面查看器 + 虚拟摄像头驱动
    "fbreitwieser/thermal-camera-android": "AI 模型与视觉",      # 安卓端热像取图与显示

    # ---- 2026-09-24：规则未命中（description 缺关键词），人工归入 ----
    "orneryd/NornicDB": "AI Agent 与 LLM 工具链",            # 图+向量混合存储底座（agent 记忆层）
    "ExpressLRS/ExpressLRS-Configurator": "飞控与无人机",      # ELRS 遥控链路配置与固件烧录
    "ExpressLRS/Backpack": "飞控与无人机",                    # ELRS 背包固件（遥控/图传共享链路）
    "AlessioMorale/crsf_parser": "飞控与无人机",              # CRSF 协议帧解析库（ELRS 链路）
    "ysoldak/HeadTracker": "飞控与无人机",                    # FPV 云台无线头部追踪器
    "Marxlp/pyFlightAnalysis": "飞控与无人机",                # 飞行日志可视化分析
    "alemidev/scope-tui": "硬件设计与 EDA",                   # 终端示波器/频谱仪（仪器类）
    "jp3141/Vector-Network-Analyzer": "硬件设计与 EDA",        # 示波器+信号源拼装的矢量网络分析仪
    "ckflight/RF_SIGNAL_GENERATOR_HARDWARE": "硬件设计与 EDA",  # 射频信号发生器开源硬件
    "lmcapacho/FPGALab": "硬件设计与 EDA",                     # 交互式虚拟 FPGA 实验台（Verilator）
    "apolkosnik/AP68040": "硬件设计与 EDA",                    # 类 MC68040 Verilog 软核 CPU
    "SanjayKumaran2805/8X8-Sequential-Multiplier-Using-Verilog": "硬件设计与 EDA",  # 时序乘法器 RTL-to-GDSII 流程
    "wigig-tools/isac-plm": "电磁仿真与超表面",                # 802.11ay/bf 通感一体物理层模型（MATLAB）
    "zhaolin820/stars-enabled-integrated-sensing-and-communications": "电磁仿真与超表面",  # RIS/STARS + ISAC 复现
    "dmcmahill/wcalc": "电磁仿真与超表面",                     # 传输线/滤波器命令行计算器（射频）
    "Prokuon/term512": "嵌入式与单片机",                       # Cardputer ADV 键盘终端扩展套件（ESP32）
    "halbeshuhn/Cardputer-WebRadio": "嵌入式与单片机",          # Cardputer 网络收音机固件
    "freewili/wilibsp": "嵌入式与单片机",                      # FreeWili 2（RP2350B）板级支持包
    "austintgriffith/picowallet": "嵌入式与单片机",             # Pico 2 W 硬件钱包（ATECC608）
    "the-can-opener/CAN-Opener-Hardware": "嵌入式与单片机",      # 低成本 CAN 总线嗅探硬件
    "InfraRecon7/IR275K": "AI 模型与视觉",                     # 遥感红外多帧超分辨基准数据集

    # ---- 2026-09-21：规则未命中（description 缺关键词），人工归入 ----
    "ElectronicCats/faultycat": "硬件设计与 EDA",  # 手动收录：全名与 desc 无硬件设计关键词
    "machmind-dev/drone-swarm-challenge-2026": "飞控与无人机",  # 手动收录：规则本命中 drone，显式固定
    "langchain-ai/rag-from-scratch": "AI Agent 与 LLM 工具链",
    "Serial-Studio/Serial-Studio": "嵌入式与单片机",
    "skiars/SerialTool": "嵌入式与单片机",
    "cantools/cantools": "嵌入式与单片机",
    "MatthewKuKanich/CAN_Commander": "嵌入式与单片机",
    "ecubus/EcuBus-Pro": "嵌入式与单片机",
    "KevinOConnor/can2040": "嵌入式与单片机",
    "CaringCaribou/caringcaribou": "嵌入式与单片机",
    "alainiamburg/sniffROM": "嵌入式与单片机",
    "cn0xroot/IFDA": "嵌入式与单片机",
    "drandyhaas/HaasoscopePro": "嵌入式与单片机",
    "cnlohr/fx3fun": "嵌入式与单片机",
    "XmanAZC/gd32c103_ab": "嵌入式与单片机",
    "enjoy-digital/litescope": "硬件设计与 EDA",
    "betaflight/betaflight-tx-lua-scripts": "飞控与无人机",
    "Plasmatree/PID-Analyzer": "飞控与无人机",
    "burakcan/MeshCore-mishmesh": "无线通信与感知",
    "hasarieddeen/TeraMIMO": "无线通信与感知",
    "MrLiuWinter/Reconfigurable-Intelligent-Surface-aided-secure-wireless-communication": "无线通信与感知",
    "mychele/toward-e2e-6g-terahertz-networks": "无线通信与感知",
    "Yuhang-Chen-TWC/DSE-SSE-demo": "无线通信与感知",
    "tak-wong/THz-AutoEncoder": "无线通信与感知",
    "danielflanigan/resonator": "电磁仿真与超表面",
    "interfas24/RAAnalysis-py": "电磁仿真与超表面",
    "udaykdk/pixelant": "电磁仿真与超表面",
    "OpenResearchInstitute/Arcanum": "电磁仿真与超表面",
    "YaleTHz/nelly": "电磁仿真与超表面",
    "dodge-research-group/thztools": "电磁仿真与超表面",
    "dodge-research-group/thz-tds-mle": "电磁仿真与超表面",
    "puls-lab/phoeniks": "电磁仿真与超表面",
    "OnderT/XoFTR": "AI 模型与视觉",
    "QiaoLiuHit/LSOTB-TIR": "AI 模型与视觉",
    "QiaoLiuHit/PTB-TIR_Evaluation_toolkit": "AI 模型与视觉",
    "RPM-Robotics-Lab/sRGB-TIR": "AI 模型与视觉",
    "HyeonJaeGil/fieldscale": "AI 模型与视觉",
    "s-du/Thermogram": "AI 模型与视觉",
    "rl-tools/rl-tools": "AI 模型与视觉",
    "Helldez/BigMoeOnEdge": "AI 模型与视觉",
    # ---- 2026-09-20：规则未命中 / 命中顺序错位，人工归入 ----
    "opencv/opencv": "AI 模型与视觉",
    "opendatalab/MinerU": "AI Agent 与 LLM 工具链",
    "colbymchenry/codegraph": "AI Agent 与 LLM 工具链",
    "lyogavin/airllm": "AI 模型与视觉",
    "maxritter/diy-thermocam": "嵌入式与单片机",
    "Tencent/wave-mcp": "硬件设计与 EDA",
    "amoslee2026/Babel": "硬件设计与 EDA",
    "gokeshenzhen/awesome-formal-verification-skill": "硬件设计与 EDA",
    "RuihongY/axi-compliance-skill": "硬件设计与 EDA",
    "estlit/SemiconductorSchool-Labs": "硬件设计与 EDA",
    "lucaong/nerves_thermal_camera": "嵌入式与单片机",
    "mlxljz/TWMM": "AI 模型与视觉",
    "browser-use/jev-ultrafast": "AI Agent 与 LLM 工具链",
    # ---- 2026-09-19：规则未命中（description 信息量不足 / 命中顺序错位），人工归入 ----
    "DroidPlanner/Tower": "飞控与无人机",
    "OpenATS/OpenATS": "飞控与无人机",
    "mathiasvr/bluejay": "飞控与无人机",
    "neoxic/ESCape32": "飞控与无人机",
    "doesthings/FreeFCC": "飞控与无人机",
    "MohammadAdib/ELRS-433": "飞控与无人机",
    "yjwong1999/Twin-TD3": "电磁仿真与超表面",
    "cactus-compute/needle": "嵌入式与单片机",
    "makerspet/oomwoo": "嵌入式与单片机",
    "vedderb/bldc": "嵌入式与单片机",
    "Neroued/ninfer": "嵌入式与单片机",
    "HarryR/z80ai": "嵌入式与单片机",
    "WangXuan95/FPGA-FOC": "嵌入式与单片机",
    "EFeru/bldc-motor-control-FOC": "嵌入式与单片机",
    "ZhuYanzhen1/miniFOC": "嵌入式与单片机",
    "verilator/verilator": "硬件设计与 EDA",
    "steveicarus/iverilog": "硬件设计与 EDA",
    "chipsalliance/chisel": "硬件设计与 EDA",
    "adam-maj/tiny-gpu": "硬件设计与 EDA",
    "MichaelGrupp/evo": "无线通信与感知",
    "introlab/rtabmap": "无线通信与感知",
    "Open-X-Humanoid/BICMap": "无线通信与感知",
    "Panasonic-Advanced-Technology/q3dweb": "无线通信与感知",
    "magicbug/Cloudlog": "无线通信与感知",
    "ggml-org/llama.cpp": "AI 模型与视觉",
    "PaddlePaddle/PaddleOCR": "AI 模型与视觉",
    # ---- 2026-09-18：规则未命中，人工归入 ----
    "google/skywater-pdk": "硬件设计与 EDA",
    "The-OpenROAD-Project/OpenROAD": "硬件设计与 EDA",
    "fguzman82/gateGPT": "嵌入式与单片机",
    "chenyuliu577-cyber/jyd-rv32i-fpga-core": "嵌入式与单片机",
    "OpenXiangShan/XiangShanLab": "嵌入式与单片机",
    "sakilxo/riscv32i-core": "嵌入式与单片机",
    "InfTape/tang-nano-20k-snn": "嵌入式与单片机",
    "kazunori279/xls32-fpga-synth": "嵌入式与单片机",
    "pavlov-net/hub75-studio": "嵌入式与单片机",
    "therealdreg/umsakazo": "电磁仿真与超表面",
    "DABIAN-afk/microstrip-studio": "电磁仿真与超表面",
    "AkitaEngineering/MeshSwarm": "无线通信与感知",
    "Galaxywalk/Wave2Body": "无线通信与感知",
    # ---- 2026-09-17：GitHub description 为空/无信息量，必须先映射再收录 ----
    "mit-han-lab/tinyml": "嵌入式与单片机",
    "AwaisShah75/Real-Time-Person-Elderly-Fall-Detection-System": "AI 模型与视觉",
    "ewine-project/UWB-localization": "无线通信与感知",
    "OpenHD/OpenHD": "飞控与无人机",
    # ---- 2026-09-17：规则未命中，人工归入 ----
    "ExpressLRS/ExpressLRS": "飞控与无人机",
    "iNavFlight/inav": "飞控与无人机",
    "makeecat/Peng": "飞控与无人机",
    "dgatf/msrc": "飞控与无人机",
    "ExpressLRS/ElrsTelemWidget": "飞控与无人机",
    "gusmanb/logicanalyzer": "硬件设计与 EDA",
    "fhdm-dev/scoppy": "硬件设计与 EDA",
    "OpenHantek/OpenHantek6022": "硬件设计与 EDA",
    "dotcypress/ula": "硬件设计与 EDA",
    "wuxx/nanoDLA": "硬件设计与 EDA",
    "nominal-io/instro": "硬件设计与 EDA",
    "xaxaxa-dev/vna": "硬件设计与 EDA",
    "jankae/VNA": "硬件设计与 EDA",
    "balmerdx/BalmerDX_VNA": "硬件设计与 EDA",
    "scott-guthridge/libvna": "硬件设计与 EDA",
    "qrp73/NanoVNA-MATLAB": "硬件设计与 EDA",
    "toammann/Multilayer_SMA2Microstrip": "电磁仿真与超表面",
    "guohuayan/WSR_maximization_for_RIS_system": "电磁仿真与超表面",
    "jimrains/OpenRIS": "电磁仿真与超表面",
    "petotamas/pyArgus": "无线通信与感知",
    "rookiepeng/beamscope": "无线通信与感知",
    "rookiepeng/arraybeam": "无线通信与感知",
    "upnalab/SonicSurface": "硬件设计与 EDA",
    "DingdongD/TDMA-MIMO": "无线通信与感知",
    "advoard/advoard_localization": "无线通信与感知",
    "groupgets/GetThermal": "AI 模型与视觉",
    "tomshaffner/PiThermalCam": "嵌入式与单片机",
    "MagnusThome/RejsaRubberTrac": "硬件设计与 EDA",
    "Eximius-Labs/fusion-embedding": "AI 模型与视觉",
    "JJN123/Fall-Detection": "AI 模型与视觉",
    "senguptaa/mmpose": "AI 模型与视觉",
    "eternity4719/HowToLiveBetter": "知识管理与笔记",
    "ArduPilot/ardupilot": "飞控与无人机",
    "bitcraze/crazyflie-firmware": "飞控与无人机",
    "ZJU-FAST-Lab/ego-planner-swarm": "飞控与无人机",
    "LGQWakkk/Quadrotor-F405": "飞控与无人机",
    "golaced/Oldx_fly_controller": "飞控与无人机",
    "pingyun001/LimeRC": "飞控与无人机",
    "SwiftWing001/swiftwing-simulation": "飞控与无人机",
    "swarm-subnet/Langostino": "飞控与无人机",
    "DroneBridge/ESP32": "飞控与无人机",
    "mavlink/MAVSDK": "飞控与无人机",
    "simonp0420/PSSFSS.jl": "电磁仿真与超表面",
    "gems-uff/pypofacets": "电磁仿真与超表面",
    "RedBlight/RaytrAMP": "电磁仿真与超表面",
    "thliebig/openEMS": "电磁仿真与超表面",
    "huobuilds/quadfs_flight_controller": "飞控与无人机",
    "chadaewoon/virtual-fpv-flight-connector": "飞控与无人机",
    "YutongChenVictor/NPU-E2E": "硬件设计与 EDA",
    "haruto89610/rtl-nic": "硬件设计与 EDA",
    "cwu766485-ctrl/LumenRV32": "嵌入式与单片机",
    "jedarden-org/whofi": "无线通信与感知",
    "hardcoreerik/OrcSDR": "无线通信与感知",
    "ivmech/pitfusion": "AI 模型与视觉",
    "pikasTech/PikaPython": "嵌入式与单片机",
    "m6c7l/pymmw": "无线通信与感知",
    "tomojitakasu/RTKLIB": "无线通信与感知",
    "SlimeVR/SlimeVR-Server": "无线通信与感知",
    "libc0607/rtl88x2eu-20230815": "无线通信与感知",
    "jelin-sh/VOFA-Protocol-Driver": "嵌入式与单片机",
    "nanomsg/nng": "开发工具与系统资源",
    "zephyrproject-rtos/zephyr": "嵌入式与单片机",
    "lvgl/lvgl": "嵌入式与单片机",
    "lvgl/lv_micropython": "嵌入式与单片机",
    "openmv/openmv": "嵌入式与单片机",
    "toitlang/toit": "嵌入式与单片机",
    "renode/renode": "嵌入式与单片机",
    "uTensor/uTensor": "嵌入式与单片机",
    "brian-smith-github/ch32v003_stt": "嵌入式与单片机",
    "sipeed/M0sense_BL702_example": "嵌入式与单片机",
    "bouffalolab/bouffalo_sdk": "嵌入式与单片机",
    "github0null/eide": "嵌入式与单片机",
    "Adancurusul/embedded-debugger-mcp": "嵌入式与单片机",
    "agentic-hil/agentic-hil": "嵌入式与单片机",
    "captainluzik/oh-my-embedded": "嵌入式与单片机",
    "pyrite-project/pyrite-ide": "嵌入式与单片机",
    "RT-Thread-Studio/sdk-bsp-ra8p1-titan-board": "嵌入式与单片机",
    "openedv/development_board_ATK-DLRK3588B": "嵌入式与单片机",
    "EIC-UESTC/aCoral": "嵌入式与单片机",
    "april/tinygo": "嵌入式与单片机",
    "American-Embedded/kistack": "硬件设计与 EDA",
    "mixelpixx/KiCAD-MCP-Server": "硬件设计与 EDA",
    "oaslananka/kicad-mcp-pro": "硬件设计与 EDA",
    "aklofas/kicad-happy": "硬件设计与 EDA",
    "atopile/atopile": "硬件设计与 EDA",
    "HakanSeven12/OpenCADStudio": "硬件设计与 EDA",
    "Open-Cascade-SAS/OCCT": "硬件设计与 EDA",
    "earthtojake/text-to-cad": "硬件设计与 EDA",
    "easyeda/easyeda-simulation-engine": "硬件设计与 EDA",
    "mercedes-benz/ardep": "硬件设计与 EDA",
    "zrrraa/X-Laser": "硬件设计与 EDA",
    "sl4v3k/Shapr3d_crack": "硬件设计与 EDA",
    "612SOG/Homebrew_parts": "硬件设计与 EDA",
    "rossant/awesome-math": "知识管理与笔记",
    "521xueweihan/HelloGitHub": "开发工具与系统资源",
    "Gonzalo-D-Sales/obsidian-velocity": "知识管理与笔记",
    "obsidian-pkm-vault/awesome-obsidian-vault": "知识管理与笔记",
    "Mintplex-Labs/anything-llm": "知识管理与笔记",
    "joeseesun/qiaomu-anything-to-notebooklm": "知识管理与笔记",
    "Graphify-Labs/graphify": "知识管理与笔记",
    "Egonex-AI/Understand-Anything": "知识管理与笔记",
    "HKUDS/DeepTutor": "知识管理与笔记",
    "bojieli/ai-agent-book": "知识管理与笔记",
    "hahhforest/pi-textbook": "知识管理与笔记",
    "buchidonggua/dg-ai-notes": "知识管理与笔记",
    "hangli-hl/AI-Articles": "知识管理与笔记",
    "rohitg00/ai-engineering-from-scratch": "知识管理与笔记",
    "byoungd/up": "知识管理与笔记",
    "K-RL/RiceBook": "知识管理与笔记",
    "pavel-kirienko/ragrag": "知识管理与笔记",
    "xianyu110/awesome-openclaw-tutorial": "AI Agent 与 LLM 工具链",
    "VoltAgent/awesome-agent-skills": "AI Agent 与 LLM 工具链",
    "multica-ai/andrej-karpathy-skills": "AI Agent 与 LLM 工具链",
    "mattpocock/skills": "AI Agent 与 LLM 工具链",
    "emilkowalski/skills": "AI Agent 与 LLM 工具链",
    "obra/superpowers": "AI Agent 与 LLM 工具链",
    "Yuan1z0825/nature-skills": "AI Agent 与 LLM 工具链",
    "skillsgate/skillsgate": "AI Agent 与 LLM 工具链",
    "zjunlp/SkillNet": "AI Agent 与 LLM 工具链",
    "affaan-m/ECC": "AI Agent 与 LLM 工具链",
    "msitarzewski/agency-agents": "AI Agent 与 LLM 工具链",
    "DietrichGebert/ponytail": "AI Agent 与 LLM 工具链",
    "lazypay/Archscribe": "AI Agent 与 LLM 工具链",
    "pbakaus/impeccable": "AI Agent 与 LLM 工具链",
    "nextlevelbuilder/ui-ux-pro-max-skill": "AI Agent 与 LLM 工具链",
    "Tiger3807861189/J-Space-Cognition-Suite-V3.7": "AI Agent 与 LLM 工具链",
    "zhaoxuya520/reverse-skill": "AI Agent 与 LLM 工具链",
    "duty1g/x64dbg-mcp-server": "AI Agent 与 LLM 工具链",
    "shinpr/mcp-image": "AI Agent 与 LLM 工具链",
    "techmanual-ai/lablink-mcp": "AI Agent 与 LLM 工具链",
    "realchendahuang/pi-config": "AI Agent 与 LLM 工具链",
    "modem-dev/hunk": "AI Agent 与 LLM 工具链",
    "Opencode-DCP/opencode-dynamic-context-pruning": "AI Agent 与 LLM 工具链",
    "github/spec-kit": "AI Agent 与 LLM 工具链",
    "openchamber/openchamber": "AI Agent 与 LLM 工具链",
    "nyc-software/qm": "AI Agent 与 LLM 工具链",
    "can1357/oh-my-pi": "AI Agent 与 LLM 工具链",
    "earendil-works/pi": "AI Agent 与 LLM 工具链",
    "hahhforest/pi": "AI Agent 与 LLM 工具链",
    "code-yeongyu/oh-my-openagent": "AI Agent 与 LLM 工具链",
    "anomalyco/opencode": "AI Agent 与 LLM 工具链",
    "openclaw/openclaw": "AI Agent 与 LLM 工具链",
    "cline/cline": "AI Agent 与 LLM 工具链",
    "QwenLM/qwen-code": "AI Agent 与 LLM 工具链",
    "HumanLayer/12-factor-agents": "AI Agent 与 LLM 工具链",
    "langchain-ai/langgraph": "AI Agent 与 LLM 工具链",
    "langchain-ai/open_deep_research": "AI Agent 与 LLM 工具链",
    "stablyai/orca": "AI Agent 与 LLM 工具链",
    "cloudflare/computer": "AI Agent 与 LLM 工具链",
    "mediar-ai/terminator": "AI Agent 与 LLM 工具链",
    "lightpanda-io/browser": "AI Agent 与 LLM 工具链",
    "h4ckf0r0day/obscura": "AI Agent 与 LLM 工具链",
    "D4Vinci/Scrapling": "AI Agent 与 LLM 工具链",
    "virattt/dexter": "AI Agent 与 LLM 工具链",
    "JrCx7scC/claude-code-source": "AI Agent 与 LLM 工具链",
    "jingyaogong/minimind": "AI 模型与视觉",
    "MakazhanAlpamys/Soup": "AI 模型与视觉",
    "superlinked/sie": "AI 模型与视觉",
    "Michael-A-Kuykendall/shimmy": "AI 模型与视觉",
    "apple-aiml-research/ml-sharp": "AI 模型与视觉",
    "IDEA-Research/Grounded-Segment-Anything": "AI 模型与视觉",
    "PufferAI/PufferLib": "AI 模型与视觉",
    "PaddlePaddle/PaddleSlim": "AI 模型与视觉",
    "Kyant0/AndroidLiquidGlass": "开发工具与系统资源",
    "swaggyliu/FlatWorld": "AI 模型与视觉",
    "Taiizor/Sucrose": "开发工具与系统资源",
    "Nutlope/logocreator": "开发工具与系统资源",
    "subframe7536/maple-font": "开发工具与系统资源",
    "TakWolf/ark-pixel-font": "开发工具与系统资源",
    "iDvel/rime-ice": "开发工具与系统资源",
    "scriptscat/scriptcat": "开发工具与系统资源",
    "DustinBrett/daedalOS": "开发工具与系统资源",
    "playcanvas/engine": "开发工具与系统资源",
    "apple/container": "开发工具与系统资源",
    "AcademySoftwareFoundation/rez": "开发工具与系统资源",
    "public-apis/public-apis": "开发工具与系统资源",
    "Free-TV/IPTV": "开发工具与系统资源",
    "vbskycn/iptv": "开发工具与系统资源",
    "MoonTechLab/LunaTV": "开发工具与系统资源",
    "hafrey1/LunaTV-config": "开发工具与系统资源",
    "hmjz100/LinkSwift": "开发工具与系统资源",
    "garinasset/leak-check": "开发工具与系统资源",
    "firecrawl/pdf-inspector": "开发工具与系统资源",
    "opendataloader-project/opendataloader-pdf": "开发工具与系统资源",
    "rossant/awesome-math2": "知识管理与笔记",
    "Hazy019/Hazy019": "开发工具与系统资源",
    "Hazy019/hazy-readme-cards": "开发工具与系统资源",
    "hongquan-prog/usbipd": "开发工具与系统资源",
    "Water-Melon/Melon": "开发工具与系统资源",
    "ap//tinygo": "嵌入式与单片机",
    "tinygo-org/tinygo": "嵌入式与单片机",
    "78/xiaozhi-esp32": "嵌入式与单片机",
    "k2-fsa/sherpa-onnx": "AI 模型与视觉",
    "mit-pdos/xv6-riscv": "开发工具与系统资源",
    "zephyrproject-rtos/zephyr ": "嵌入式与单片机",
    "american-embedded/kistack": "硬件设计与 EDA",
    # 热点推荐项目的校正
    "lightorigins/LightNav-0": "飞控与无人机",
    "modm-io/modm": "嵌入式与单片机",
    "zer011b/fdtd3d": "电磁仿真与超表面",
    "korvin011/CSTMWS-Matlab-Interface": "电磁仿真与超表面",
    "kaankvrck/Cst-Py-Api": "电磁仿真与超表面",
    "flexcompute/tidy3d": "电磁仿真与超表面",
    "hzzg0727/Metasurface-Design": "电磁仿真与超表面",
    "youxch/Inverse-design-of-metasurfaces": "电磁仿真与超表面",
    "loganwilliams/thermografree": "硬件设计与 EDA",
    "HUYATIEO/silk-fpga": "硬件设计与 EDA",
    "Eriemon/verilog-generator": "硬件设计与 EDA",
    "Kevincoooool/OpenMV_PCB": "硬件设计与 EDA",
    "nathanfarlow/univac-1219-riscv": "开发工具与系统资源",
    "jonathanmuller/esp-ppb": "无线通信与感知",
    "renesas-rdk/rzv2h_drone_px4": "飞控与无人机",
    "Fratres-X-AI/JamBoy": "飞控与无人机",
    "piecol/LEVIA-H7": "飞控与无人机",
    "raylanlin/smarttune-cli": "飞控与无人机",
    "kavishka-dot/vulcan-os": "嵌入式与单片机",
    "lalitshankarch/rvcore": "嵌入式与单片机",
    "karagure/rvkit": "嵌入式与单片机",
    "tenstorrent/rv_tester": "嵌入式与单片机",
    "stlink-org/stlink": "嵌入式与单片机",
    "lvgl/lv_esp_idf": "嵌入式与单片机",
    # 2026-09-16 热点推荐项目校正（规则未命中，逐个指定）
    "HKUST-Aerial-Robotics/Fast-Planner": "飞控与无人机",
    "amaranth-lang/amaranth": "硬件设计与 EDA",
    "SystemRDL/PeakRDL": "硬件设计与 EDA",
    "pico-coder/sigrok-pico": "嵌入式与单片机",
    "lxydiy/LiThermal": "硬件设计与 EDA",
    "OpenThermal/libseek-thermal": "硬件设计与 EDA",
    "leswright1977/PyThermalCamera": "硬件设计与 EDA",
    "LeoDJ/P2Pro-Viewer": "硬件设计与 EDA",
    "LJMUAstroecology/flirpy": "硬件设计与 EDA",
    "Clothooo/lvt2calib": "硬件设计与 EDA",
    "SalahAssana/5G-SCG": "无线通信与感知",
    "KylinC/mmVital-Signs": "无线通信与感知",
    "edwin-pan/uDoppler-Classification": "无线通信与感知",
    "FanJunqiao/M4Human": "无线通信与感知",
    "cliansang/positioning-algorithms-for-uwb-matlab": "无线通信与感知",
    "matthuszagh/pyems": "电磁仿真与超表面",
    "Shallot-2009/Ketupa": "电磁仿真与超表面",
    "profdc9/ModularTuner": "电磁仿真与超表面",
    "Beate-Suy-Zhang/EvoFuse": "AI 模型与视觉",
    "Scientist888-star/GDAFusion": "AI 模型与视觉",
}

UNCLASSIFIED = "待归类"


def _text(entry: dict) -> str:
    parts = [
        entry.get("full_name", ""),
        entry.get("description") or "",
        " ".join(entry.get("topics") or []),
        entry.get("language") or "",
    ]
    return " ".join(parts).lower()


def classify(entry: dict) -> str:
    if entry["full_name"] in OVERRIDES:
        return OVERRIDES[entry["full_name"]]
    hay = _text(entry)
    for cat in CATEGORIES:
        for kw in RULES.get(cat, []):
            if kw.lower() in hay:
                return cat
    return UNCLASSIFIED


def _norm_star(row: dict) -> dict:
    return {
        "full_name": row["full_name"],
        "url": row.get("html_url") or f"https://github.com/{row['full_name']}",
        "description": (row.get("description") or "").strip(),
        "language": row.get("language") or "",
        "stars": row.get("stars") or 0,
        "topics": row.get("topics") or [],
        "archived": bool(row.get("archived")),
        "source": "star",
        "added_at": (row.get("starred_at") or "")[:10] or date.today().isoformat(),
    }


def _norm_rec(row: dict) -> dict:
    url = row["url"].strip()
    full = url.replace("https://github.com/", "").strip("/")
    return {
        "full_name": full,
        "url": url,
        "description": (row.get("desc") or "").strip(),
        "language": "",
        "stars": row.get("stars") or 0,
        "topics": [],
        "archived": False,
        "source": "hot",
        "added_at": row.get("date") or date.today().isoformat(),
    }


def load_existing() -> dict[str, dict]:
    if REPOS.exists():
        data = json.loads(REPOS.read_text(encoding="utf-8"))
        return {r["full_name"]: r for r in data.get("repos", [])}
    return {}


def main() -> int:
    reclassify = "--reclassify" in sys.argv
    existing = load_existing()
    added_star = added_hot = 0

    stars_file = DATA / "stars_raw.json"
    if stars_file.exists():
        for line in stars_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = _norm_star(json.loads(line))
            cur = existing.get(row["full_name"])
            if cur:
                # 刷新动态字段，保留分类与人工备注
                for k in ("description", "language", "stars", "topics", "archived", "url"):
                    cur[k] = row[k]
                if reclassify and not cur.get("manual_category"):
                    cur["category"] = classify(cur)
            else:
                row["category"] = classify(row)
                row["note"] = ""
                existing[row["full_name"]] = row
                added_star += 1

    rec_file = DATA / "recommendations.jsonl"
    if rec_file.exists():
        for line in rec_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = _norm_rec(json.loads(line))
            cur = existing.get(row["full_name"])
            if cur:
                if row["stars"]:
                    cur["stars"] = row["stars"]
                if not cur.get("description"):
                    cur["description"] = row["description"]
                if reclassify and not cur.get("manual_category"):
                    cur["category"] = classify(cur)
                cur["sources"] = sorted(set(cur.get("sources", ["star"])) | {row["source"]})
                # 热点推荐过的 star 项目也记一笔来源日期
                cur.setdefault("hot_dates", [])
                if row["added_at"] not in cur["hot_dates"]:
                    cur["hot_dates"].append(row["added_at"])
            else:
                row["category"] = classify(row)
                row.setdefault("applicable", "")
                row["note"] = ""
                existing[row["full_name"]] = row
                added_hot += 1

    repos = sorted(existing.values(), key=lambda r: (CATEGORIES.index(r["category"]) if r.get("category") in CATEGORIES else 99, -r.get("stars", 0)))

    DATA.mkdir(exist_ok=True)
    REPOS.write_text(
        json.dumps({"updated_at": date.today().isoformat(), "repos": repos}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"写入 {REPOS.relative_to(ROOT)}：共 {len(repos)} 个仓库（star 新增 {added_star}，热点新增 {added_hot}）")

    if "--report" in sys.argv:
        from collections import Counter

        cnt = Counter(r["category"] for r in repos)
        print("\n分类统计：")
        for c in CATEGORIES:
            print(f"  {c}: {cnt.get(c, 0)}")
        if cnt.get(UNCLASSIFIED):
            print(f"  {UNCLASSIFIED}: {cnt[UNCLASSIFIED]}")
            for r in repos:
                if r["category"] == UNCLASSIFIED:
                    print("    -", r["full_name"], "|", r["description"][:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
