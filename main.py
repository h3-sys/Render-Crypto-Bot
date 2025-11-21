# =====================================================
# Render 托管代码 (main.py) - 最终版
# =====================================================

# 1. 导入必要的库
from flask import Flask
from threading import Thread
import os 
import time

import ccxt
import pandas as pd
import telebot 
import io 
from datetime import datetime, timedelta

# =====================================================
# 📌 配置区：从 Render 环境变量读取
# =====================================================
# Bot Token 和 Chat ID 将从 Render 界面设置的 Secret 中获取
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID")

# 检查环境变量是否设置 (Bot 启动时会打印警告)
if not TELEGRAM_BOT_TOKEN or not TARGET_CHAT_ID:
    print("❌ 错误：TELEGRAM_BOT_TOKEN 或 TARGET_CHAT_ID 环境变量未设置！请检查 Render 配置。")

# 初始化 Bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False) # 在 Render Worker 中通常不需要多线程

# =====================================================
# 📌 核心函数：获取 Binance 合约 K 线 (返回字符串)
# =====================================================
def fetch_futures_kline_binance(
    symbol="BTC/USDT", 
    bar="1h",          
    limit=5,
    preview_rows=5
):
    # ------------------------------------------------------------------
    # 关键机制：捕获 print 输出到字符串中
    # ------------------------------------------------------------------
    import sys
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()

    # ---------------------------
    # 1️⃣ 初始化交易所并获取 K 线
    # ---------------------------
    
    api_symbol = symbol.replace('/', '') 
    
    exchange = ccxt.binanceusdm()
    
    try:
        raw_data = exchange.fetch_ohlcv(
            api_symbol, 
            timeframe=bar,
            limit=limit
        )
    except Exception as e:
        print(f"❌ API 请求失败。请检查符号 ({symbol}) 或周期 ({bar}) 是否有效。错误: {e}")
        # 恢复标准输出并返回错误信息
        sys.stdout = old_stdout
        return f"❌ 数据获取失败，错误信息：{e}"


    if not raw_data:
        sys.stdout = old_stdout
        return f"❌ 警告：API 返回数据为空，请检查币种({symbol})或周期({bar})是否正确。"

    # ---------------------------
    # 2️⃣ 数据处理和格式化
    # ---------------------------
    columns = ["Open Time", "Open", "High", "Low", "Close", "Volume"]
    df = pd.DataFrame(raw_data, columns=columns)

    df["Open Time"] = pd.to_datetime(df["Open Time"], unit="ms")
    df["Open Time (UTC+8)"] = (
        df["Open Time"]
        .dt.tz_localize("UTC")
        .dt.tz_convert("Asia/Shanghai")
    )
    
    df_preview = df.tail(preview_rows).copy()
    df_preview['Time'] = df_preview["Open Time (UTC+8)"].dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 格式化
    df_preview['Volume'] = df_preview['Volume'].round(4)
    df_preview['Open'] = df_preview['Open'].round(1)
    df_preview['High'] = df_preview['High'].round(1)
    df_preview['Low'] = df_preview['Low'].round(1)
    df_preview['Close'] = df_preview['Close'].round(1)
    
    final_cols = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    df_preview = df_preview[final_cols]

    # ---------------------------
    # 3️⃣ 生成 AI 友好格式输出
    # ---------------------------
    now_ts_shanghai = pd.Timestamp.now(tz='Asia/Shanghai')
    now_str = now_ts_shanghai.strftime("%Y-%m-%d %H:%M:%S UTC+8")
    
    last_candle_open_time = df_preview['Time'].iloc[-1]
    is_last_candle_open = (
        pd.to_datetime(last_candle_open_time) < now_ts_shanghai.tz_localize(None)
    )

    print("================= AI 可复制内容 =================\n")
    print(f"#当前时间：{now_str}")
    print(f"#交易所：Binance U本位合约 (Futures)") 
    print(f"#币种：{symbol}")
    print(f"#周期：{bar}")
    print(f"#注意：所有时间 (Time) 均为北京时间 (UTC+8)。") 
    
    if is_last_candle_open:
        print(f"#重要提示：表格中的最后一行 K 线 ({last_candle_open_time}) 尚未收盘，其收盘价 (Close) 为实时价格，High/Low 仍可能变化。")
    
    print(f"#数据条数：最近 {df.shape[0]} 条 (展示 {preview_rows} 条)\n")

    print(df_preview.to_string(index=False))

    print("\n#请结合以上数据继续分析。")
    print("\n=================================================\n")
    
    # 恢复标准输出并返回捕获到的字符串
    sys.stdout = old_stdout
    return redirected_output.getvalue()


# =====================================================
# 📌 Telegram Bot 处理器 (命令定义)
# =====================================================

# 检查权限的辅助函数
def check_permission(message):
    return str(message.chat.id) == TARGET_CHAT_ID

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "欢迎使用数据获取Bot！\n发送 /get_btc 获取最新的 BTC/USDT 1小时合约数据。\n发送 /get_eth 获取 ETH/USDT 4小时合约数据。")

@bot.message_handler(commands=['get_btc'])
def get_btc_data(message):
    if not check_permission(message):
        bot.send_message(message.chat.id, "抱歉，您无权操作此Bot。")
        return
        
    try:
        bot.send_message(message.chat.id, "⏳ 正在获取 BTC/USDT 1h 数据，请稍候...")
        
        result_string = fetch_futures_kline_binance(
            symbol="BTC/USDT",
            bar="1h",
            limit=10,
            preview_rows=10
        )
        
        bot.send_message(message.chat.id, result_string)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ 数据获取失败：{e}")

@bot.message_handler(commands=['get_eth'])
def get_eth_data(message):
    if not check_permission(message):
        bot.send_message(message.chat.id, "抱歉，您无权操作此Bot。")
        return

    try:
        bot.send_message(message.chat.id, "⏳ 正在获取 ETH/USDT 4h 数据，请稍候...")
        
        result_string = fetch_futures_kline_binance(
            symbol="ETH/USDT",
            bar="4h",
            limit=10,
            preview_rows=10
        )
        
        bot.send_message(message.chat.id, result_string)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ 数据获取失败：{e}")


# =====================================================
# 📌 启动 Bot 监听器
# =====================================================

# 仅保留 Bot 启动，Render 不需 Keep-Alive Web Server
if __name__ == '__main__':
    print("🚀 Telegram Bot 监听器启动...")
    # infinity_polling 会保持进程不退出，符合 Render Worker 的要求
    bot.infinity_polling(none_stop=True)
